import os
from pathlib import Path
from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename
import traceback

from claim_parser import get_converter, extract_claim_data

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB limit

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize converter globally so it doesn't reload on each request
print("Initializing document converter...")
converter, setup_warnings = get_converter()
print("Converter initialized.")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    if file and file.filename.lower().endswith('.pdf'):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        try:
            # Process the PDF using claim_parser
            master_data = extract_claim_data(file_path, converter, setup_warnings)
            
            # Clean up the file after processing
            if os.path.exists(file_path):
                os.remove(file_path)
                
            return jsonify(master_data)
        except Exception as e:
            traceback.print_exc()
            # Clean up file in case of error
            if os.path.exists(file_path):
                os.remove(file_path)
            return jsonify({'error': str(e)}), 500
            
    return jsonify({'error': 'Invalid file type. Only PDF is allowed.'}), 400

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
