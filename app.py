import os
import time
import uuid
import json
import requests
from flask import Flask, request, jsonify
import boto3

app = Flask(__name__)

S3_BUCKET = "random-files-storage"
AWS_REGION = "ap-south-1"
LANGUAGE_CODE = "en-US"
AWS_ACCESS_KEY_ID = "test"
AWS_SECRET_ACCESS_KEY = "test"

s3_client = boto3.client(
    's3',
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)
transcribe_client = boto3.client(
    'transcribe',
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)


@app.route('/transcribe', methods=['POST'])
def transcribe_audio():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided in request with key 'file'."}), 400
    file = request.files['file']
    if file.filename == "":
        return jsonify({"error": "Empty filename provided."}), 400
    filename = file.filename
    ext = filename.split('.')[-1].lower()
    if ext not in ['mp3', 'mp4', 'wav', 'flac']:
        return jsonify({"error": f"Unsupported audio format: {ext}. Supported formats: mp3, mp4, wav, flac."}), 400
    media_format = ext
    unique_id = str(uuid.uuid4())
    s3_key = f"audio/{unique_id}.{ext}"
    try:
        s3_client.upload_fileobj(file, S3_BUCKET, s3_key)
    except Exception as e:
        return jsonify({"error": f"Error uploading file to S3: {str(e)}"}), 500
    media_uri = f"s3://{S3_BUCKET}/{s3_key}"
    transcription_job_name = f"transcription-{unique_id}"
    try:
        transcribe_client.start_transcription_job(
            TranscriptionJobName=transcription_job_name,
            Media={'MediaFileUri': media_uri},
            MediaFormat=media_format,
            LanguageCode=LANGUAGE_CODE
        )
    except Exception as e:
        return jsonify({"error": f"Failed to start transcription job: {str(e)}"}), 500
    while True:
        try:
            job = transcribe_client.get_transcription_job(
                TranscriptionJobName=transcription_job_name)
        except Exception as e:
            return jsonify({"error": f"Error getting transcription job status: {str(e)}"}), 500
        status = job['TranscriptionJob']['TranscriptionJobStatus']
        if status in ['COMPLETED', 'FAILED']:
            break
        time.sleep(5)
    if status == 'FAILED':
        message = job['TranscriptionJob'].get('FailureReason', 'Unknown error')
        return jsonify({"error": f"Transcription job failed: {message}"}), 500
    transcript_file_uri = job['TranscriptionJob']['Transcript']['TranscriptFileUri']
    try:
        transcript_response = requests.get(transcript_file_uri)
        transcript_response.raise_for_status()
        transcript_json = transcript_response.json()
        transcript_text = transcript_json.get('results', {}).get(
            'transcripts', [{}])[0].get('transcript', '')
    except Exception as e:
        return jsonify({"error": f"Failed to retrieve transcript: {str(e)}"}), 500
    return jsonify({
        "transcription_job_name": transcription_job_name,
        "transcript": transcript_text
    })


if __name__ == '__main__':
    app.run(debug=True)
