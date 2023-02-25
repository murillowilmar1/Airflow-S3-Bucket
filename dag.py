from airflow import DAG, XComArg
from airflow.decorators import task
import pendulum
from airflow.providers.amazon.aws.operators.s3 import (
S3CopyObjectOperator, S3ListOperator, S3DeleteObjectsOperator
)
from airflow.providers.amazon.aws.hooks.s3 import S3Hook



# define ingest and destination buckets
S3_INGEST_BUCKET = "caxe-demo-bucket"
S3_INTEGER_BUCKET = "caxe-demo-bucket/example-integer-bucket"
S3_NOT_INTEGER_BUCKET = "caxe-demo-bucket/example-not-integer-bucket"

with DAG(
  dag_id="AWS-S3",
  start_date=pendulum.datetime(2022, 10, 10, tz="UTC"),
  schedule=None,
  catchup=False,
  doc_md=__doc__,
):
   

# fetch the file names from the ingest S3 bucket
    list_files_ingest_bucket = S3ListOperator(
          task_id="list_files_ingest_bucket",
           aws_conn_id="aws_default",
           bucket=S3_INGEST_BUCKET
           )
   

    @task

    def read_keys_form_s3(source_key_list):
        """Fetch the contents from all files in the S3_INGEST_BUCKET."""
        s3_hook = S3Hook(aws_conn_id='aws_default')
        print(source_key_list)
        content_list = []
        for key in source_key_list:
            file_content = s3_hook.read_key(
                key=key,
                bucket_name=S3_INGEST_BUCKET
        )
        content_list.append(file_content)
 
        return content_list
# read the contents from all files in the ingest bucket
    content_list = read_keys_form_s3(XComArg(list_files_ingest_bucket))



    @task

    def test_if_integer(content_list):
        """Tests the content of each file for whether it is an integer."""
        destination_list = []
        for file_content in content_list:
            if isinstance(file_content, int):
              destination_list.append(S3_INTEGER_BUCKET)
            else:
              destination_list.append(S3_NOT_INTEGER_BUCKET)
        return destination_list
# create a list of destinations based on the content in the files
    dest_key_list = test_if_integer(content_list)

    @task

    def generate_source_dest_pairs(source_key_list, dest_key_list):
        """Create an XComArg containing a list of dicts.
         The dicts contain the source and destination bucket keys for
         each file in the ingest bucket.q
        """
        list_of_source_dest_pairs = []
        for s, d in zip(source_key_list, dest_key_list):
         list_of_source_dest_pairs.append(
             {
            "source_bucket_key": f"s3://{S3_INGEST_BUCKET}/{s}",
            "dest_bucket_key": f"s3://{d}/{s}"
             }
         )     
        return list_of_source_dest_pairs
# generates the list of dicts to pass to the expand_kwargs argument
# of the copy_files_S3 task
    source_dest_pairs = generate_source_dest_pairs(
    XComArg(list_files_ingest_bucket),
    dest_key_list
    )


# dynamically copy all files into either the S3_INTEGER_BUCKET or the
# S3_NOT_INTEGER_BUCKET. One task per file.

    copy_files_S3 = S3CopyObjectOperator.partial(
    task_id="copy_files_S3",
    aws_conn_id="aws_default"
    ).expand_kwargs(source_dest_pairs)


# dynamically delete the files in the ingest bucket. One task per file.

    delete_content_ingest_bucket = S3DeleteObjectsOperator.partial(
     task_id="delete_content_ingest_bucket",
     aws_conn_id="aws_default",
     bucket=S3_INGEST_BUCKET
     ).expand(keys=XComArg(list_files_ingest_bucket))




# set dependencies not set by the TaskFlowAPI
copy_files_S3 >> delete_content_ingest_bucket