from flask import Flask, request, jsonify
from pymongo import MongoClient
from flask_cors import CORS
# from transformers import DistilBertTokenizer, DistilBertForSequenceClassification
# import torch
import requests
import os


app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "http://localhost:8080"}})

# tokenizer = DistilBertTokenizer.from_pretrained('distilbert-base-uncased')
# model = DistilBertForSequenceClassification.from_pretrained('distilbert-base-uncased', num_labels=2)
# model.eval()

client = MongoClient("mongodb://localhost:27017/")
db = client["jira-issues"]
collectionJiraProjects = db["jiraProject"]
collectionJiraIssues = db["jiraIssue"]
collectionFeedback = db["feedback"]
collectionFeedbackAssigned = db["feedback_assigned"]

@app.route('/update_all_issues', methods=['GET'])
def update_all_issues():
    issues = list(collectionJiraIssues.find())

    for issue in issues:
        # Suchen Sie Feedbacks, die mit dem aktuellen Issue übereinstimmen
        query = {"left_feedback_issue": issue["summary"]}
        feedbacks = list(collectionFeedbackAssigned.find(query))

        if feedbacks:
            # Finden Sie das Feedback mit dem höchsten match_score
            highest_score_feedback = max(feedbacks, key=lambda x: x["match_score"])

            # Aktualisieren Sie das Issue mit dem gefundenen Feedback
            collectionJiraIssues.update_one({"_id": issue["_id"]},
                                        {"$set": {"right_feedback_issue": highest_score_feedback["right_feedback_issue"]}})

    return jsonify({"message": "Feedback updated"})


@app.route("/hitec/jira/feedback-assigned/load", methods=["GET"])
def load_feedback_assigned():
    feedback = list(collectionFeedbackAssigned.find({}))
    for element in feedback:
        element["_id"] = str(element["_id"])
    return feedback


# @app.route('/save-feedback', methods=['POST'])
# def save_feedback():
#     feedback = request.json.get('feedback')
#
#     # classify with distilbert
#     inputs = tokenizer(feedback, return_tensors='pt', padding=True, truncation=True)
#     with torch.no_grad():
#         outputs = model(**inputs)
#     predicted_label = torch.argmax(outputs.logits).item()
#     predicted_category = "bug" if predicted_label == 0 else "feature"
#
#     # save in MongoDB
#     feedback_data = {'text': feedback, 'category': predicted_category}
#     collectionFeedback.insert_one(feedback_data)
#
#     return jsonify({'message': 'Feedback saved and classified successfully.'})


@app.route("/hitec/jira/feedback/load", methods=["GET"])
def load_feedback():
    feedback = list(collectionFeedback.find({}))
    for element in feedback:
        element["_id"] = str(element["_id"])
    return feedback


@app.route('/save_excel_data', methods=['POST'])
def save_excel_data():
    excel_data = request.json.get('data')

    if excel_data:
        try:
            for row in excel_data:
                id_value = row[1]
                feedback_value = row[2]
                collectionFeedback.insert_one(
                    {'ID': id_value, 'Feedback': feedback_value})  # Jede Zeile einzeln in die Datenbank einfügen
            return jsonify({'message': 'Excel data saved successfully'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    else:
        return jsonify({'error': 'No data provided'}), 400


@app.route("/hitec/jira/issues/load/issueTypes/<project_name>")
def load_issue_types_from_jira_issues(project_name):
    issue_types = []

    try:
        base_url = "https://jira-se.ifi.uni-heidelberg.de"
        uri = f"{base_url}/rest/api/2/search?jql=project={project_name}&maxResults=10000"

        response = requests.get(
            uri,
            auth=(os.environ['username'], os.environ['password']),
            headers={"Accept": "application/json"}
        )
        response_json = response.json()
        set_new_project_names(response_json["issues"][0]["fields"]["project"]["name"])
        total_issues = int(response_json.get("total", 0))

        for i in range(total_issues):
            issue_type = response_json["issues"][i]["fields"]["issuetype"]["name"]
            if issue_type not in issue_types:
                issue_types.append(issue_type)

    except Exception as e:
        pass

    return issue_types


def set_new_project_names(project_name):
    filter_query = {"name": project_name}
    # matching_elements = list(collectionJiraProjects.find(filter_query))

    if list(collectionJiraProjects.find(filter_query)):
        return jsonify({"message": "Einträge mit dem Namen 'test' gefunden."})
    else:
        collectionJiraProjects.insert_one(filter_query)


@app.route("/hitec/jira/issues/load/issues/<project_name>", methods=["POST"])
def load_issues_from_project(project_name):
    data = request.json
    list = []

    issue_types = [item["item"] for item in data["jsonObject"]]

    for issue_type in issue_types:
        uri = f"https://jira-se.ifi.uni-heidelberg.de/rest/api/2/search?jql=project={project_name} AND issuetype='{issue_type}'&maxResults=520"
        response = requests.get(
            uri,
            auth=(os.environ['username'], os.environ['password']),
            headers={"Accept": "application/json"}
        )

        response_json = response.json()
        total_issues = int(response_json.get("total", 0))

        for i in range(total_issues):
            issue_key = response_json["issues"][i]["key"]
            issue_type = response_json["issues"][i]["fields"]["issuetype"]["name"]
            project_name = response_json["issues"][i]["fields"]["project"]["name"]
            summary = response_json["issues"][i]["fields"]["summary"]
            issue = {"key": issue_key, "issueType": issue_type, "projectName": project_name, "summary": summary}
            list.append(issue)

    return jsonify(list)


@app.route("/hitec/jira/issues/import", methods=["POST"])
def import_jira_issues():
    data = request.json
    collectionJiraIssues.delete_many({})
    saved_issues = []

    for item in data["jsonObject"]:
        key = item["key"]
        project_name = item["projectName"]
        issue_type = item["issueType"]
        summary = item["summary"]
        jira_issue = {
            "key": key,
            "issueType": issue_type,
            "projectName": project_name,
            "summary": summary
        }
        saved_issue = collectionJiraIssues.insert_one(jira_issue)
        saved_issue_info = {
            "inserted_id": str(saved_issue.inserted_id),
            "key": key,
            "issueType": issue_type,
            "projectName": project_name,
            "summary": summary
        }
        saved_issues.append(saved_issue_info)

    return jsonify(saved_issues)


@app.route("/hitec/jira/issues/add", methods=["POST"])
def add_jira_issues():
    data = request.json
    saved_issues = list(collectionJiraIssues.find({}))

    for item in data["jsonObject"]:
        key = item["key"]
        project_name = item["projectName"]
        issue_type = item["issueType"]
        summary = item["summary"]
        jira_issue = {
            "key": key,
            "issueType": issue_type,
            "projectName": project_name,
            "summary": summary
        }
        already_used = any(jira_issue["key"] == key for jira_issue in saved_issues)
        if not already_used:
            collectionJiraIssues.insert_one(jira_issue)

    updated_issues = list(collectionJiraIssues.find({}))
    for element in updated_issues:
        element["_id"] = str(element["_id"])

    return jsonify(updated_issues)


@app.route("/hitec/jira/issues/all", methods=["GET"])
def get_all_jira_issues_from_db():
    try:
        page = int(request.args.get("page", default=1))
        size = int(request.args.get("size", default=-1))

        if size == -1:
            size = collectionJiraIssues.count_documents({})

        skip = (page - 1) * size
        cursor = collectionJiraIssues.find().skip(skip).limit(size)

        issues = list(cursor)
        for issue in issues:
            issue["_id"] = str(issue["_id"])
        if issues:
            total_items = collectionJiraIssues.count_documents({})
            total_pages = (total_items + size - 1) // size
            res = {
                "issues": issues,
                "currentPage": page,
                "totalItems": total_items,
                "totalPages": total_pages
            }
        else:
            res = {
                "issues": issues,
                "currentPage": page,
                "totalItems": 0,
                "totalPages": 0
            }

        return jsonify(res), 200


    except Exception as e:
        return jsonify({"error": "Internal Server Error"}), 500


@app.route("/hitec/jira/projectNames", methods=["GET"])
def get_all_project_names():
    project_names = list(collectionJiraProjects.find({}))
    for element in project_names:
        element["_id"] = str(element["_id"])
    return project_names


if __name__ == '__main__':
    app.run(debug=True)
