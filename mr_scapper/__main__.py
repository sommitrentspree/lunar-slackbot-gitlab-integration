from pprint import pprint
import gitlab
from slack import WebClient
import timeago, datetime
from dateutil import parser
import os

gl_token = os.getenv('GITLAB_TOKEN')
slack_token = os.getenv('STACK_USER_OAUTH_TOKEN')
slack_channel_id = 'lunar-gitlab-bot'
team = 'team:lunar'

gl_x_slack_username_map = {
    'pongpich1': 'pongpich',
    'chodanun1': 'chodanun',
    'ong.ittiwat': 'ittiwat',
    'songyos-rentspree': 'songyos',
    'premwutt': 'premwut',
    'sommit1': 'sommit',
}

now = datetime.datetime.now()

slclient = WebClient(token=slack_token)

gl = gitlab.Gitlab(private_token=gl_token)
gl.auth()

mrs = gl.mergerequests.list(
    scope='all',
    state='opened',
    get_all=True,
    labels=team,
)

draft_msgs = []
review_msgs = []

for mr in mrs:
    print('--------------------------------------------------------')
    print('title: ', mr.title) # string
    print('description: ', mr.description) # string
    print('source_branch: ', mr.source_branch) # string
    print('target_branch: ', mr.target_branch) # string
    print('has_conflicts: ', mr.has_conflicts)  # boolean
    print('blocking_discussions_resolved: ', mr.blocking_discussions_resolved) # boolean
    print('draft: ', mr.draft) # boolean
    print('web_url: ', mr.web_url) # string
    print('user_notes_count: ', mr.user_notes_count) # int , comments
    print('merge_status: ', mr.merge_status == 'can_be_merged') # boolean
    print('references_full: ', mr.references['full']) # string
    print('created_at: ', mr.created_at) # date string
    print('author_username: ', mr.author['username']) # string
    print('author_name: ', mr.author['name']) # string

    status = ''
        
    if mr.draft:
        status += '🔨'
    else:
        if mr.has_conflicts:
            status += '🟡'
        
        if len(status) == 0:
            status = '🟢'

    tag_slack_usernames = ''
    
    if not mr.draft:
        if mr.has_conflicts:
            slack_username = gl_x_slack_username_map.get(mr.author['username'])
            tag_slack_usernames = '<@%s>' % slack_username
        else:
            approvals = gl.projects.get(mr.project_id).mergerequests.get(mr.iid).approvals.get()
            
            if approvals.approvals_left == 0:
                continue
            
            if len(mr.reviewers) == 0:
                continue
            
            approved_by = {}
            
            for a in approvals.approved_by:
                approved_by[a['user']['username']] = 1
                
            for reviewer in mr.reviewers:
                print('reviewer_username: ', reviewer['username']) # string
                print('reviewer_name: ', reviewer['name']) # string
                
                if approved_by.get(reviewer['username']) == 1:
                    continue
                
                slack_username = gl_x_slack_username_map.get(reviewer['username'])
                
                if slack_username is not None:
                    tag_slack_usernames += '\n\t\t- <@%s>' % slack_username
            
            if len(tag_slack_usernames) == 0:
                continue
    
    # repo_name = mr.references['full'].split('/')[-1].replace(mr.references['short'], '')

    msg = '%s [%s] <%s|%s> %s' % (
        status, 
        timeago.format(
            parser.parse(mr.created_at).timestamp(),
            now.timestamp(),
        ), 
        mr.web_url,
        mr.source_branch,
        tag_slack_usernames,
    )
    
    if mr.draft:
        draft_msgs.append(msg)
    else:
        review_msgs.append(msg)

sum_msg = ''

if len(draft_msgs) > 0:
    draft_msgs.insert(0, '***In progress ....')
    sum_msg += '\n'.join(draft_msgs)
    sum_msg += '\n'

if len(review_msgs) > 0:
    review_msgs.insert(0, '***Please review ....')
    sum_msg += '\n'.join(review_msgs)
    sum_msg += '\n'
    
pprint(sum_msg)

slclient.chat_postMessage(
  channel=slack_channel_id,
  text=sum_msg
)
