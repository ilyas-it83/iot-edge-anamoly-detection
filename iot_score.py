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

import os

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

def run(input_df):
    import json
    import pandas

    #input_json = json.loads(input_str)

    #input_df = pandas.DataFrame([[input_json['machine']['temperature'], \
    #   input_json['machine']['pressure'], \
    #   input_json['ambient']['temperature'], \
    #   input_json['ambient']['humidity'], \
    #   ]])

    output=None
    orig_json=None
    print(input_df)
    inputs_dc.collect(input_df)

    pred = model.predict(input_df)
    prediction_dc.collect(pred)

    print("Prediction is ", pred[0])
    orig_json= input_df.to_json(orient='records')[1:-1].replace('},{', '} {')
    if pred[0] == '1':
        output = orig_json[:-1] + ",'anamoly':true}"
    else:
        output = orig_json[:-1] + ",'anamoly':false}"

    return output


def main():
  from azureml.api.schema.dataTypes import DataTypes
  from azureml.api.schema.sampleDefinition import SampleDefinition
  from azureml.api.realtime.services import generate_schema
  import pandas

  # Anomaly
  df = pandas.DataFrame(data=[[33.66995566, 2.44341267, 21.39450979, 26]], columns=['machine_temperature', \
    'machine_pressure','ambient_temperature','ambient_humidity'])

  # Turn on data collection debug mode to view output in stdout
  os.environ["AML_MODEL_DC_DEBUG"] = 'true'

  # Test the output of the functions
  init()
  # Anomaly
  #input1 = '{ "machine": { "temperature": 33.66995566, "pressure": 2.44341267 }, \
  #      "ambient": { "temperature": 21.39450979, "humidity": 26 },\
  #      "timeCreated": "2017-10-27T18:14:02.4911177Z" }'

  # Normal
  #input1 = '{ "machine": { "temperature": 31.16469009, "pressure": 2.158002669 }, \
  #  "ambient": { "temperature": 21.17794693, "humidity": 25 },\
  #   "timeCreated": "2017-10-27T18:14:02.4911177Z" }'
  
  input2 = pandas.DataFrame(data=[[31.16469009, 2.158002669, 21.17794693, 25]], columns=['machine_temperature', \
    'machine_pressure','ambient_temperature','ambient_humidity'])

  print("Result: " + str(run(input2)))

  inputs = {"input_df": SampleDefinition(DataTypes.PANDAS, df)}
  generate_schema(run_func=run, inputs=inputs, filepath='./outputs/service_schema.json')
  
  print("Schema generated")

if __name__ == "__main__":
    main()