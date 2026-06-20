import requests

try:
    response = requests.post("http://127.0.0.1:8000/api/initialize", json={
        'provider_id': 'mimo',
        'base_url': 'https://api.xiaomimimo.com/v1',
        'api_key': '',
        'model': 'mimo-v2.5',
        'display_name': '大哥',
        'target_language': '日语',
        'exam_id': 'cjt4',
        'exam_name': '大学日语四级',
        'learning_goal': '通过考试',
        'learning_background': '高中日语',
        'search_years': 3
    })
    print("Status code:", response.status_code)
    print("Response text:", response.text)
except Exception as e:
    print("Exception:", e)
