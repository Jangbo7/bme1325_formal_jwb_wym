from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import urllib.request
import urllib.error

DEEPSEEK_KEY = '277149ebe53440a190ee02bd66673cd1'
DEEPSEEK_MODEL = 'deepseek-v3:671b'
DEEPSEEK_URL = 'https://api.deepseek.com/v1/chat/completions'

QWEN_KEY = '7cbf678f86e24121864883fd950e3449'
QWEN_MODEL = 'qwen2.5-vl-instruct'
QWEN_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions'

DASHSCOPE_KEY = 'sk-361f43ece66a49e299a35ef26ac687d7'
DASHSCOPE_MODEL = 'qwen2.5-vl-instruct'
DASHSCOPE_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions'

SYSTEM_PROMPT = '你是一个医院分诊台的智能护士。请根据患者描述给出简短分诊建议，必要时提醒急诊。回答简洁，1-3句话。'


def call_deepseek(message):
    payload = {
        'model': DEEPSEEK_MODEL,
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': message}
        ],
        'temperature': 0.7,
        'max_tokens': 500
    }
    req = urllib.request.Request(
        DEEPSEEK_URL,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {DEEPSEEK_KEY}'
        }
    )
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode('utf-8'))
        return data['choices'][0]['message']['content']


def call_qwen(message, image_data=None, use_dashscope=False):
    model = DASHSCOPE_MODEL if use_dashscope else QWEN_MODEL
    url = DASHSCOPE_URL if use_dashscope else QWEN_URL
    key = DASHSCOPE_KEY if use_dashscope else QWEN_KEY

    if image_data:
        content = [
            {'type': 'image_url', 'image_url': {'url': image_data}},
            {'type': 'text', 'text': message}
        ]
    else:
        content = message

    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': content}
        ],
        'temperature': 0.7,
        'max_tokens': 500
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {key}'
        }
    )
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode('utf-8'))
        return data['choices'][0]['message']['content']


class APIProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.path = '/index.html'
        try:
            with open('.' + self.path, 'rb') as f:
                content = f.read()
            if self.path.endswith('.html'):
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
            elif self.path.endswith('.js'):
                self.send_response(200)
                self.send_header('Content-type', 'application/javascript')
            elif self.path.endswith('.css'):
                self.send_response(200)
                self.send_header('Content-type', 'text/css')
            else:
                self.send_response(200)
                self.send_header('Content-type', 'application/octet-stream')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_response(404)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write('404 Not Found'.encode('utf-8'))

    def do_POST(self):
        if self.path == '/api/chat':
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                request_data = json.loads(post_data.decode('utf-8'))
                message = request_data.get('message', '')
                model = request_data.get('model', 'deepseek')
                image_data = request_data.get('image')

                if model == 'deepseek':
                    response_text = call_deepseek(message)
                elif model == 'qwen':
                    response_text = call_qwen(message, None, use_dashscope=True)
                elif model == 'qwen-vl':
                    response_text = call_qwen(message, image_data, use_dashscope=True)
                else:
                    response_text = call_deepseek(message)

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'response': response_text}, ensure_ascii=False).encode('utf-8'))
            except urllib.error.HTTPError as e:
                error_body = e.read().decode('utf-8')
                self.send_response(502)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'error': error_body}, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}, ensure_ascii=False).encode('utf-8'))
        else:
            self.send_response(404)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'Not Found'}).encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def log_message(self, format, *args):
        return


if __name__ == '__main__':
    port = 8000
    httpd = HTTPServer(('', port), APIProxyHandler)
    print(f'服务器运行在 http://localhost:{port}')
    print('API代理端点: http://localhost:8000/api/chat')
    httpd.serve_forever()
