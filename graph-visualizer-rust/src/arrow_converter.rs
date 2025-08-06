use anyhow::Result;
use arrow::array::RecordBatch;
use arrow::ipc::writer::StreamWriter;
use arrow::ipc::writer::IpcWriteOptions;
use bytes::Bytes;

pub struct ArrowConverter;

impl ArrowConverter {
    pub fn record_batch_to_bytes(batch: &RecordBatch) -> Result<Bytes> {
        let mut buffer = Vec::new();
        {
            let options = IpcWriteOptions::default();
            let mut writer = StreamWriter::try_new_with_options(
                &mut buffer, 
                &batch.schema(),
                options
            )?;
            writer.write(batch)?;
            writer.finish()?;
        }
        Ok(Bytes::from(buffer))
    }
    
    pub fn record_batch_to_json(batch: &RecordBatch) -> Result<String> {
        let mut json_rows = Vec::new();
        
        for row_idx in 0..batch.num_rows() {
            let mut row = serde_json::Map::new();
            
            for (col_idx, field) in batch.schema().fields().iter().enumerate() {
                let column = batch.column(col_idx);
                let value = arrow_array_value_to_json(column, row_idx)?;
                row.insert(field.name().clone(), value);
            }
            
            json_rows.push(serde_json::Value::Object(row));
        }
        
        Ok(serde_json::to_string(&json_rows)?)
    }
}

fn arrow_array_value_to_json(array: &dyn arrow::array::Array, index: usize) -> Result<serde_json::Value> {
    use arrow::array::*;
    use arrow::datatypes::DataType;
    
    if array.is_null(index) {
        return Ok(serde_json::Value::Null);
    }
    
    match array.data_type() {
        DataType::Utf8 => {
            let array = array.as_any().downcast_ref::<StringArray>().unwrap();
            Ok(serde_json::Value::String(array.value(index).to_string()))
        }
        DataType::Int32 => {
            let array = array.as_any().downcast_ref::<Int32Array>().unwrap();
            Ok(serde_json::Value::Number(array.value(index).into()))
        }
        DataType::UInt32 => {
            let array = array.as_any().downcast_ref::<UInt32Array>().unwrap();
            Ok(serde_json::Value::Number(array.value(index).into()))
        }
        DataType::Float64 => {
            let array = array.as_any().downcast_ref::<Float64Array>().unwrap();
            let value = array.value(index);
            Ok(serde_json::Number::from_f64(value)
                .map(serde_json::Value::Number)
                .unwrap_or(serde_json::Value::Null))
        }
        _ => Ok(serde_json::Value::String(format!("{:?}", array.data_type()))),
    }
}