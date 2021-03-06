import os
import json
import time
import logging
import tempfile
import argparse

from flask import (
    Flask, render_template, url_for, request, g, redirect,
    Response,
)

from problem import (
    get_problems,
    get_problem_by_url_name,
    get_problem_by_pid,
    get_new_problem,
    state2name,
)
from runner import (
    Failed,
    Controller,
    run,
)
from submission import (
    get_submissions,
    get_submission_by_sid,
)
from category import get_categories
from db import get_cursor

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/problems')
def problems():
    args = request.args
    order_by = args.get('order_by', 'id')
    return render_template('problems.html', problems=get_problems(order_by))

@app.route('/categories')
def categories():
    return render_template('categories.html', categories=get_categories())

@app.route('/submissions')
def submissions():
    return render_template('submissions.html', submissions=get_submissions())

@app.route('/submission/<sid>')
def submission(sid):
    return render_template('submission.html',
                           submission=get_submission_by_sid(sid))

@app.route('/problem/<url_name>')
def problem(url_name):
    p = get_problem_by_url_name(url_name)
    logging.debug('get problem {}'.format(p.pid))
    if not p:
        return render_template('404.html'), 404
    return render_template('problem.html', problem=p)

@app.route('/edit-problem/<url_name>')
def edit_problem(url_name):
    p = get_problem_by_url_name(url_name)
    if not p:
        return render_template('404.html'), 404
    return render_template('edit-problem.html', problem=p)

@app.route('/submit-problem', methods=['POST'])
def submit_problem():
    '''Create new problem or update existing problem'''
    r = json.loads(request.form['data'])
    p = get_problem_by_pid(r['pid'])
    try:
        p.submit(r)
        return json.dumps({'result': 'ok',
                           'redirect': '/problem/{}'.format(p.url_name)})
    except ValueError as e:
        return json.dumps({'result': 'error', 'message': e.message})

@app.route('/new-problem')
def new_problem():
    return render_template('edit-problem.html',
                           problem=get_new_problem(), is_new_problem=True)

@app.route('/submit-code', methods=['POST'])
def submit_code():
    pid = request.form['pid']
    title = request.form['title']
    lang = request.form['lang']
    code = request.form['code']
    print 'submit_code', title
    try:
        sid = run(pid, title, lang, code)
        return json.dumps({
            'result': 'ok',
            'sid': sid,
        })
        return str(sid)
    except Failed as e:
        print 'failed:', e.message
        return json.dumps({
            'result': 'failed',
            'message': e.message,
        })
    except Exception as e:
        print e

@app.route('/last-submission-code')
def last_submission_code():
    pid = request.args.get('pid', None)
    lang = request.args.get('lang', None)
    if pid is None or lang is None:
        return ''
    else:
        return get_problem_by_pid(int(pid)).last_submission_code(lang)

@app.route('/submission-state/<sid>')
def submission_state(sid):
    def pull_state():
        print 'pulling state'
        c = get_cursor()
        while True:
            c.execute('select state, info from submission where rowid = ?',
                      (sid,))
            r = c.fetchone()
            if r is None:
                break
            else:
                state, info = r
                yield 'data: {}\n\n'.format(json.dumps({
                    'state': state,
                    'name': state2name(state),
                    'info': info or '',
                }))
                if state != 'pending':
                    print '=' * 20, 'result ok', state
                    break
            time.sleep(0.2)
    return Response(pull_state(), mimetype='text/event-stream')

@app.context_processor
def override_url_for():
    return dict(url_for=dated_url_for)

def dated_url_for(endpoint, **vals):
    if endpoint == 'static':
        filename = vals.get('filename', None)
        if filename:
            file_path = os.path.join(app.root_path, endpoint, filename)
            vals['q'] = int(os.stat(file_path).st_mtime)
    return url_for(endpoint, **vals)

@app.teardown_appcontext
def close_db(error):
    if hasattr(g, 'db'):
        g.db.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('port', type=int, nargs='?', default=80,
                        help='port number, defaults to 80')
    parser.add_argument('host', type=str, nargs='?', default='localhost',
                        help='host ip, defaults to localhost')
    args = parser.parse_args()

    logging.basicConfig(format='%(asctime)-15s %(levelname)s %(message)s',
                        level=logging.DEBUG)
    controller = Controller()
    tempfile.tempdir = 'runtime/temp/'

    app.run(host=args.host, port=args.port, threaded=True, debug=True)
