# This script generates the scoring file
# with the init and run functions needed to
# operationalize the anomaly detection sample
import json
import os
import random
import sys
import time
import iothub_client
from iothub_client import IoTHubError, IoTHubModuleClient
from iothub_client import IoTHubTransportProvider
from iothub_client import IoTHubMessageDispositionResult

from azureml.api.schema.dataTypes import DataTypes
from azureml.api.schema.sampleDefinition import SampleDefinition
from azureml.api.realtime.services import generate_schema
import pandas

# Import data collection library. Only supported for docker mode.
# Functionality will be ignored when package isn't found
try:
    from azureml.datacollector import ModelDataCollector
except ImportError:
    print("Data collection is currently only supported in docker mode. May be disabled for local mode.")
    # Mocking out model data collector functionality

    class ModelDataCollector(object):
        def nop(*args, **kw): pass
        def __getattr__(self, _): return self.nop
        def __init__(self, *args, **kw): return None
    pass



# messageTimeout - the maximum time in milliseconds until a message times out.
# The timeout period starts at IoTHubModuleClient.send_event_async.
# By default, messages do not expire.
MESSAGE_TIMEOUT = 10000

# global counters
RECEIVE_CALLBACKS = 0
SEND_CALLBACKS = 0
TEMPERATURE_THRESHOLD = 10
TWIN_CALLBACKS = 0

# Choose HTTP, AMQP or MQTT as transport protocol.  Currently only MQTT is supported.
PROTOCOL = IoTHubTransportProvider.MQTT

# Callback received when the message that we're forwarding is processed.


def send_confirmation_callback(message, result, user_context):
    print("Reieved confirmation callback")
    global SEND_CALLBACKS
    print("Confirmation[%d] received for message with result = %s" % (
        user_context, result))
    map_properties = message.properties()
    key_value_pair = map_properties.get_internals()
    print("    Properties: %s" % key_value_pair)
    SEND_CALLBACKS += 1
    print("    Total calls confirmed: %d" % SEND_CALLBACKS)

# receive_message_callback is invoked when an incoming message arrives on the specified
# input queue (in the case of this sample, "input1").  Because this is a filter module,
# we forward this message to the "output1" queue.

def receive_message_callback(message, hubManager):
    print("Reieved message callback")
    global RECEIVE_CALLBACKS
    global TEMPERATURE_THRESHOLD
    message_buffer = message.get_bytearray()
    size = len(message_buffer)
    message_text = message_buffer[:size].decode('utf-8')
    print("    Data: <<<%s>>> & Size=%d" % (message_text, size))
    map_properties = message.properties()
    key_value_pair = map_properties.get_internals()
    print("    Properties: %s" % key_value_pair)
    RECEIVE_CALLBACKS += 1
    print("    Total calls received: %d" % RECEIVE_CALLBACKS)
    data = json.loads(message_text)
    if "machine" in data and "temperature" in data["machine"] and data["machine"]["temperature"] > TEMPERATURE_THRESHOLD:
        map_properties.add("MessageType", "Alert")
        print("Machine temperature %s exceeds threshold %s" %
              (data["machine"]["temperature"], TEMPERATURE_THRESHOLD))
    output_json = json.dumps(run(data))
    hubManager.forward_event_to_output("output1", output_json, 0)
    return IoTHubMessageDispositionResult.ACCEPTED

# module_twin_callback is invoked when the module twin's desired properties are updated.
def module_twin_callback(update_state, payload, user_context):
    print("Reieved module_twin callback")
    global TWIN_CALLBACKS
    global TEMPERATURE_THRESHOLD
    print("\nTwin callback called with:\nupdateStatus = %s\npayload = %s\ncontext = %s" % (
        update_state, payload, user_context))
    data = json.loads(payload)
    if "desired" in data and "TemperatureThreshold" in data["desired"]:
        TEMPERATURE_THRESHOLD = data["desired"]["TemperatureThreshold"]
    if "TemperatureThreshold" in data:
        TEMPERATURE_THRESHOLD = data["TemperatureThreshold"]
    TWIN_CALLBACKS += 1
    print("Total calls confirmed: %d\n" % TWIN_CALLBACKS)


class HubManager(object):

    def __init__(
            self,
            protocol=IoTHubTransportProvider.MQTT):
        self.client_protocol = protocol
        self.client = IoTHubModuleClient()
        self.client.create_from_environment(protocol)

        # set the time until a message times out
        self.client.set_option("messageTimeout", MESSAGE_TIMEOUT)

        # sets the callback when a message arrives on "input1" queue.  Messages sent to
        # other inputs or to the default will be silently discarded.
        self.client.set_message_callback(
            "input1", receive_message_callback, self)
        # Sets the callback when a module twin's desired properties are updated.
        self.client.set_module_twin_callback(module_twin_callback, self)

    # Forwards the message received onto the next stage in the process.
    def forward_event_to_output(self, outputQueueName, event, send_context):
        self.client.send_event_async(
            outputQueueName, event, send_confirmation_callback, send_context)

# Prepare the web service definition by authoring
# init() and run() functions. Test the functions
# before deploying the web service.


def init():
    global inputs_dc, prediction_dc
    from sklearn.externals import joblib

    # load the model file
    global model
    model = joblib.load('model.pkl')

    inputs_dc = ModelDataCollector("model.pkl", identifier="inputs")
    prediction_dc = ModelDataCollector("model.pkl", identifier="prediction")


def run(input_str):
    input_json = json.loads(input_str)

    input_df = pandas.DataFrame([[input_json['machine']['temperature'],
        input_json['machine']['pressure'],
        input_json['ambient']['temperature'],
        input_json['ambient']['humidity'],
        ]])

    print(input_df)
    inputs_dc.collect(input_df)

    pred = model.predict(input_df)
    prediction_dc.collect(pred)

    print("Prediction is ", pred[0])

    if pred[0] == '1':
        input_json['anomaly'] = True
    else:
        input_json['anomaly'] = False

    return json.dumps(input_json)


def main(protocol):

  try:
        print("\nPython %s\n" % sys.version)
        print("IoT Hub Client for Python")
        hub_manager = HubManager(protocol)
        print ( "Starting the IoT Hub Python sample using protocol %s..." % hub_manager.client_protocol )
        print ( "The sample is now waiting for messages and will indefinitely.  Press Ctrl-C to exit. ")

        while True:
            time.sleep(1)
  except IoTHubError as iothub_error:
        print ( "Unexpected error %s from IoTHub" % iothub_error )
        return
  except KeyboardInterrupt:
        print ( "IoTHubModuleClient sample stopped" )

  # Anomaly
  df = pandas.DataFrame(data=[[33.66995566, 2.44341267, 21.39450979, 26]], columns=['machine_temperature','machine_pressure','ambient_temperature','ambient_humidity'])

  # Turn on data collection debug mode to view output in stdout
  os.environ["AML_MODEL_DC_DEBUG"] = 'false'

  # Test the output of the functions
  init()

  # Anomaly
  input1 = '{ "machine": { "temperature": 33.66995566, "pressure": 2.44341267 }, \
        "ambient": { "temperature": 21.39450979, "humidity": 26 },\
        "timeCreated": "2017-10-27T18:14:02.4911177Z" }'
  
  # Normal
  # input1 = '{ "machine": { "temperature": 31.16469009, "pressure": 2.158002669 }, \
  #      "ambient": { "temperature": 21.17794693, "humidity": 25 },\
  #     "timeCreated": "2017-10-27T18:14:02.4911177Z" }'

  #print("Result: " + run(input1))
  
  inputs = {"input_df": SampleDefinition(DataTypes.PANDAS, df)}
  generate_schema(run_func=run, inputs=input1, filepath='./outputs/service_schema.json')

  
if __name__ == "__main__":
    main(PROTOCOL)
