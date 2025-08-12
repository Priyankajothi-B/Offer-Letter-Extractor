from flask import Flask, render_template, request, send_from_directory, url_for, redirect
from werkzeug.utils import secure_filename
import os
import pandas as pd
from extractor import extract_from_pdf

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

RESULTS_FILE = "results.xlsx"

app = Flask(__name__, static_folder="uploads")
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB limit

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", results=None, error=None, message=None)

@app.route("/upload", methods=["POST"])
def upload():
    files = request.files.getlist("file")
    if not files:
        return render_template("index.html", error="No files uploaded", results=None)

    extracted_results = []
    for file in files:
        if file and file.filename.lower().endswith(".pdf"):
            filename = secure_filename(file.filename)
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(save_path)
            try:
                result = extract_from_pdf(save_path)
                result["filename"] = filename
                result["pdf_url"] = url_for("uploaded_file", filename=filename)
                extracted_results.append(result)
            except Exception as e:
                extracted_results.append({
                    "filename": filename,
                    "name": None,
                    "company": None,
                    "salary": None,
                    "pdf_url": url_for("uploaded_file", filename=filename),
                    "error": str(e)
                })
        else:
            extracted_results.append({
                "filename": file.filename,
                "name": None,
                "company": None,
                "salary": None,
                "pdf_url": None,
                "error": "Invalid file type"
            })

    return render_template("index.html", results=extracted_results, error=None)

@app.route("/save_all", methods=["POST"])
def save_all():
    filenames = request.form.getlist("filename")
    names = request.form.getlist("name")
    companies = request.form.getlist("company")
    salaries = request.form.getlist("salary")

    rows = []
    for i in range(len(filenames)):
        rows.append({
            "Filename": filenames[i],
            "Name": names[i],
            "Company": companies[i],
            "Salary": salaries[i]
        })

    try:
        if os.path.exists(RESULTS_FILE):
            df = pd.read_excel(RESULTS_FILE)
            df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)
        else:
            df = pd.DataFrame(rows)
        df.to_excel(RESULTS_FILE, index=False)
        return redirect(url_for("index"))
    except Exception as e:
        return render_template("index.html", results=None, error=str(e))

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == "__main__":
    app.run(debug=True)
