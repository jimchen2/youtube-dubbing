from flask import Flask, request, jsonify
import os
from functools import wraps
from run import process_video

app = Flask(__name__)

API_SECRET = os.getenv('API_SECRET') 

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if api_key and api_key == API_SECRET:
            return f(*args, **kwargs)
        return jsonify({'error': 'Invalid or missing API key'}), 401
    return decorated_function

@app.route('/process-video', methods=['POST'])
@require_api_key
def process_video_endpoint():
    app.logger.info('Received request')
    data = request.get_json()
    
    if not data or 'video_url' not in data:
        app.logger.error('Missing video_url')
        return jsonify({'error': 'video_url is required'}), 400
    
    video_url = data['video_url']
    target_lang = data.get('target_lang', 'ru')
    
    app.logger.info(f'Processing video: {video_url} with target language: {target_lang}')
    
    try:
        result = process_video(video_url, target_lang)
        
        if result:
            app.logger.info(f'Processing successful: {result}')
            return jsonify({
                'status': 'success',
                's3_url': result
            })
        else:
            app.logger.error('Processing failed')
            return jsonify({
                'status': 'error',
                'message': 'Processing failed or no translation needed'
            }), 400
    except Exception as e:
        app.logger.error(f'Error processing request: {str(e)}')
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
