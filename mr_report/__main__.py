from functools import cmp_to_key
import os
from datetime import datetime
import timeago
import gitlab
from dateutil import parser
from slack import WebClient

gl_token = os.getenv('GITLAB_TOKEN')
slack_token = os.getenv('STACK_USER_OAUTH_TOKEN')
slack_channel_id = 'lunar-gitlab-bot'
team = 'team:lunar'

def timeago_no_suffix(timestamp1, timestamp2) -> str:
    return timeago.format(
        timestamp1,
        timestamp2,
    ).replace(' ago', '')
    
def duration(timestamp1, timestamp2) -> int:
    return timestamp2 - timestamp1

def custom_sort(arr, key, type = 1):
    return sorted(arr,key=cmp_to_key(lambda x, y: x[key] - y[key] if type == 1 else y[key] - x[key]))


now = datetime.now() # TODO: set timezone

slclient = WebClient(token=slack_token)

gl = gitlab.Gitlab(private_token=gl_token)
gl.auth()

# ---------- collecting stats ----------

mrs = gl.mergerequests.list(
    scope='all',
    labels=team,
    created_after=datetime(2022, 10, 1, 0, 0, 0), # TODO: set timezone
    get_all=True,
)

draft_mrs = []
opened_with_no_draft_mrs = []
merged_mrs = []

for mr in mrs:
    if mr.state == 'closed':
        continue
    
    _mr = {
        'title': mr.title,
        'source_branch': mr.source_branch,
        'target_branch': mr.target_branch,
        'has_conflicts': mr.has_conflicts,
        'web_url': mr.web_url,
        'created_at': parser.parse(mr.created_at),
    }
    
    if mr.state == 'merged':
        _mr['age'] = timeago_no_suffix(
            parser.parse(mr.created_at).timestamp(),
            parser.parse(mr.merged_at).timestamp(),
        )
        
        _mr['age_duration'] = duration(
            parser.parse(mr.created_at).timestamp(),
            parser.parse(mr.merged_at).timestamp(),
        )
    else:
        _mr['age'] = timeago_no_suffix(
            parser.parse(mr.created_at).timestamp(),
            now.timestamp(),
        )
        
        _mr['age_duration'] = duration(
            parser.parse(mr.created_at).timestamp(),
            now.timestamp(),
        )
    
    mr_detail = gl.projects.get(mr.project_id).mergerequests.get(mr.iid)
    _mr['changed_files'] = mr_detail.changes_count
    
    commits = mr_detail.commits()
    _mr['commits_count'] = len(commits)
    
    approvals = mr_detail.approvals.get()
    _mr['approved_count'] = len(approvals.approved_by)
    
    notes = mr_detail.notes.list(
        order_by='created_at',
        sort='asc',
        get_all=True,
    )
    
    _mr['comments'] = []
    
    for note in notes:
        if note.type == 'DiffNote' and not note.system and note.resolvable:
            _note = {
                'resolved': note.resolved,
                'created_at': parser.parse(note.created_at),
            }
            
            if note.resolved:
                _note['resolved_at'] = parser.parse(note.resolved_at),
                
                _note['age'] = timeago_no_suffix(
                    parser.parse(note.created_at).timestamp(),
                    parser.parse(note.resolved_at).timestamp(),
                )
            else:
                _note['age'] = timeago_no_suffix(
                    parser.parse(note.created_at).timestamp(),
                    now.timestamp(),
                )
            
            _mr['comments'].append(_note)
                    
    if mr.draft:
        draft_mrs.append(_mr)
    else:
        if mr.state == 'opened':
            opened_with_no_draft_mrs.append(_mr)
        elif mr.state == 'merged':
            merged_mrs.append(_mr)

draft_mrs = custom_sort(draft_mrs, 'age_duration', 1)
opened_with_no_draft_mrs = custom_sort(opened_with_no_draft_mrs, 'age_duration', 1)
merged_mrs = custom_sort(merged_mrs, 'age_duration', 1)

# ---------- notify to slack ----------

# *** draft mrs
# *** opening mrs
# *** merged mrs
# [2 days] lnr-1000 (10 commits, 8 files, 2 approved)
# comments
# • 🕗 05102022_0750 - age 3 hours
# • ✅ 05102022_0750 - age 3 hours
# [2 days] lnr-1000 (2) (1 commits, 1 files, 0 approved)

def build_mr_message(mr: dict) -> str:
    msg = '[%s] <%s|%s> (%d commits, %s files, %d approved)\n' % (
        mr['age'],
        mr['web_url'],
        mr['source_branch'],
        mr['commits_count'],
        mr['changed_files'],
        mr['approved_count'],
    )
    
    for comment in mr['comments']:
        msg += '• %s %s - age %s\n' % (
            '✅' if comment['resolved'] else '🕗', 
            comment['created_at'].strftime('%d%m%Y_%H%M'), 
            comment['age'],
        )
    
    return msg

sum_msg = ''

# draft
sum_msg += '**** draft mrs ****\n'
for mr in draft_mrs:
    sum_msg += build_mr_message(mr)
    
# opening
sum_msg += '\n**** opening mrs ****\n'
for mr in opened_with_no_draft_mrs:
    sum_msg += build_mr_message(mr)
    
# merged
sum_msg += '\n**** merged mrs ****\n'
for mr in merged_mrs:
    sum_msg += build_mr_message(mr)

slclient.chat_postMessage(
  channel=slack_channel_id,
  text=sum_msg
)
