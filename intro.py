from flask import Flask, request, redirect
from flask_sqlalchemy import SQLAlchemy
import io
import os
import hashlib
import pandas as pd
import requests
from delorean import parse

app = Flask("intro")
DATABASE_DEFAULT = "postgres://epbfddrayozxxg:b9cb2db4bf5151f07e7b4deccd310d80dd3840500cf74549f56a398d57cf59b4@ec2-54-83-51-38.compute-1.amazonaws.com:5432/dfh7gmt30l91bc"
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', DATABASE_DEFAULT)
db = SQLAlchemy(app)
font_size = "10"
pd.set_option('display.max_colwidth', -1)

from functools import wraps
from flask import request, Response

def display_results(query):
 result = db.session.execute(query)
 db.session.commit()
 final_result = []
 if "UPDATE" not in query:
  for rowproxy in result:
   final_result.append(dict(rowproxy.items()))
  return final_result
 else:
  return False

def check_auth(username, password):
 """This function is called to check if a username /
 password combination is valid.
 """
 return username == 'staff' and password == 'congress123'

def authenticate():
 """Sends a 401 response that enables basic auth"""
 return Response(
 'Could not verify your access level for that URL.\n'
 'You have to login with proper credentials', 401,
 {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
 @wraps(f)
 def decorated(*args, **kwargs):
  auth = request.authorization
  if not auth or not check_auth(auth.username, auth.password):
   return authenticate()
  return f(*args, **kwargs)
 return decorated

with open("tdlista.txt","r") as my_file:
 text = [line.replace("\n","").split("\t") for line in my_file.readlines()]
 df = pd.DataFrame(text, columns=["Name","agaid","memtype","rating","expiry","club","state","sigma","joined"])
 df['agaid'] = df['agaid'].astype("str")

def get_email_hash(id, year, is_user=False):
 if not is_user:
  resp = display_results("SELECT email FROM attendees WHERE id=" + str(id) + " AND year=" + str(year)  + ";")
 else:
  resp = display_results("SELECT email FROM users WHERE id=" + str(id) + " AND year=" + str(year) + ";")
 if len(resp) == 1:
  email = resp[0]['email']
 else:
  return False
 hash_object = hashlib.sha1(email.encode('utf-8'))
 return hash_object.hexdigest()

def is_int(s):
 try:
  my_int = int(s)
  return True
 except ValueError:
  return False

def get_user(attendee_id):
 result = display_results("SELECT user_id FROM attendees WHERE id=" + attendee_id + ";")
 if len(result) != 1:
  return False
 else:
  return result[0]['user_id']

def is_checked_in(attendee_id):
 result = display_results("SELECT checked_in FROM attendees WHERE id=" + str(attendee_id) + " AND year=2018;")
 return result[0]['checked_in']

def get_atts_from_user(user_id, year, inc_cancel=False):
 if not inc_cancel:
  cancel_phrase = " AND cancelled=False"
 else:
  cancel_phrase = ""
 resp = display_results("SELECT id FROM attendees WHERE user_id=" + str(user_id) + " AND year=" + str(year) + cancel_phrase  + ";")
 all_attendees = []
 for elem in resp:
  all_attendees.append(elem['id'])
 return all_attendees

@app.route("/invoice")
def invoice():
 attendee_id = request.args.get('attendee_id')
 year = request.args.get('year')
 return get_invoice_total(attendee_id,year,is_user=False)
 

def get_invoice_total(id, year, is_user=False):
 if not is_user:
  cur_user = get_user(id)
  if not cur_user:
   return False
 else:
  cur_user = id
 all_atts = get_atts_from_user(cur_user, year, inc_cancel=True)
 if len(all_atts) == 0:
  return False
  
 where_statement = "("
 for att in all_atts:
  where_statement += "(attendee_id=" + str(att) + ") OR "
 where_statement = where_statement[:-4] + ")"
 all_plans = display_results("SELECT attendee_id,plan_id,quantity,year FROM attendee_plans WHERE " + where_statement + " AND year=" + year + ";")
 sum_total = 0
 for plan in all_plans:
  sum_total += float(get_price_from_id("plans",plan['plan_id'],year)) * int(plan['quantity'])
 all_activities = display_results("SELECT attendee_id,activity_id,year FROM attendee_activities WHERE " + where_statement + " AND year=" + year + ";")
 for activity in all_activities:
  sum_total += float(get_price_from_id("activities",activity['activity_id'],year))
 return sum_total

def get_price_from_id(type, id, year):
 temp_results = display_results("SELECT price FROM " + type + " WHERE id=" + str(id) + " AND year=" + str(year) + ";")
 return temp_results[0]['price']

def get_paid_total(id, year):
 cur_user = id
 all_trans = display_results("SELECT trantype,amount FROM transactions WHERE user_id=" + str(cur_user) + " AND year=" + str(year) + ";")
 all_refund = 0
 all_comp = 0
 all_sale = 0
 for tran in all_trans:
  if tran['trantype'] == "R":
   all_refund += tran['amount']
  elif tran['trantype'] == "C":
   all_comp += tran['amount']
  elif tran['trantype'] == "S":
   all_sale += tran['amount']
 return all_sale,all_comp,all_refund

def check_aga_member(df, id, year):
 results = display_results("SELECT aga_id,given_name,family_name FROM attendees WHERE id=" + str(id) + " AND year=" + str(year) + ";")
 if len(results) == 1:
  if results[0]['aga_id']:
   return results[0]['aga_id']
  else:
   full_name = results[0]['family_name'].capitalize() + ", " + results[0]['given_name']
   member = df[(df['Name'] == full_name.strip())]
   if len(member) == 1:
    return member['agaid'].tolist()[0]
 return False

def is_current_membership(df, aga_id):
 if not aga_id:
  no_aga_id = True
  return False,False,False
 else:
  member = df[(df['agaid'].str.strip() == str(aga_id))]
  if len(member) == 0:
   aga_id_not_found = True
   return False,False,False
  else:
   db_datetime = parse(member['expiry'].tolist()[0], dayfirst=False, yearfirst=False).date
   end_date = parse("July 28th, 2018").date
   if db_datetime < end_date:
    return False,db_datetime,True
 return True,db_datetime,False
 
def get_name_from_id(id):
 results = display_results("SELECT given_name,family_name FROM attendees WHERE id=%s" % id)
 return results[0]['given_name'] + " " + results[0]['family_name']


@app.route("/testadv",methods=['GET','POST'])
@requires_auth
def testadv():
 global df
 temp_output_df = []
 attendee_id = request.args.get('attendee_id')
 user_id = request.args.get('user_id')
 year = request.args.get('year')
 email_hash = request.args.get('hash')
 is_resync = request.args.get('is_resync')
 temp_basic_df = []

 if is_resync == "true":
  temp_basic_df.append("AGA Member Database Resynced")
  df = resync()

 aga_id_error = False
 minor_bad = False
 membership_notes = ""
 construct_row = ['','','','','','','','','','','','']
 
 if year and is_int(year):
  if user_id and not attendee_id:
   is_user = True
   id = user_id
   all_atts = get_atts_from_user(id, year)
  elif attendee_id and not user_id:
   is_user = False
   id = attendee_id
   user_id = get_user(id)
   all_atts = get_atts_from_user(user_id, year)
  else:
   return "<style>body{background-color: red}</style>You're trying to break me! You didn't enter a valid attendee_id/user_id or you tried to enter both! Bad boy, you failed!"
  if len(all_atts) == 0:
   temp_basic_df.append("DATABASE SAYS ALL ATTENDEES UNDER CURRENT USER ACCOUNT HAVE CANCELLED.")
   return "<style>body{background-color: yellow}</style>" + str(temp_basic_df)
  if not attendee_id:
   temp_basic_df.append("Number of attendees attempting to check in at once: " + str(len(all_atts)))
  else:
   temp_basic_df.append("Number of attendees attempting to check in at once: 1")
  basic_df = pd.DataFrame(temp_basic_df, columns=["Basic Information"])
  
  all_paid = get_paid_total(user_id, year)
  if not all_paid and all_paid != 0:
   return "<style>body{background-color: red}</style>You're trying to break me! Bad boy, you failed!"
  # Combine comp and paid together
  user_paid = all_paid[0]/100 + all_paid[1]/100
  # Get refund
  user_refund = all_paid[2]/100
  paid_and_refund = user_paid + user_refund
  invoice_total = get_invoice_total(id, year, is_user=is_user)
  if not invoice_total and invoice_total != 0:
   return "<style>body{background-color: red}</style>You're trying to break me! Bad boy, you failed!"
  else:
   invoice_total = invoice_total/100
  total_due = invoice_total - user_paid + user_refund
  if total_due > -0.5 and total_due < 0.5:
   total_due = 0
  format = ''
  if attendee_id:
   all_atts = [attendee_id]
  # Check their memberships
  for att in all_atts:
   try:
    result = display_results("SELECT * FROM attendees WHERE id=" + str(att) + " AND year=" + str(year) + ";")[0]
   except:
    continue
   construct_row = ['','',result['given_name'],result['family_name'],'','',invoice_total,paid_and_refund,total_due,result['understand_minor'],result['minor_agreement_received'],result['checked_in']]
   aga_id = check_aga_member(df, att, year)
   is_expired = True
   if aga_id:
    construct_row[4] = aga_id
    is_member,member_expiry,is_expired = is_current_membership(df,aga_id)
    construct_row[5] = str(is_member) + " - Expires: " + str(member_expiry)
   else:
    construct_row[4] = "NOT FOUND"
    construct_row[5] = "N/A"
   if not email_hash:
    return "<style>body{background-color: red}</style>Your hash is missing!"
   else:
    site_hash = get_email_hash(id, year, is_user=is_user)
    if not site_hash:
     return "<style>body{background-color: red}</style>System error! User ID not found!"
    elif email_hash != site_hash:
     return "<style>body{background-color: red}</style>Hashes don't match!"
   if construct_row[8] <= 0 and construct_row[4] != "NOT FOUND" and is_member and not is_expired and not ((construct_row[9] == True) and (construct_row[10] == False)):
    if not is_checked_in(att):
     construct_row[0] = "GOOD"
     construct_row[1] = "No problems"
    else:
     construct_row[0] = "99% GOOD"
     construct_row[1] = "Attendee ALREADY Checked In!"
   else:
    construct_row[0] = "PROBLEM"
    
    if construct_row[8] > 0:
     construct_row[1] += "SIGN-IN FAILED: Money is owed to the Congress<br/>"
    if construct_row[4] == "NOT FOUND":
     construct_row[1] += "SIGN-IN FAILED: Could not find AGA ID<br/>"
    if is_expired:
     construct_row[1] += "SIGN-IN FAILED: AGA ID has expired!<br/>"
    if (construct_row[9] == True) and (construct_row[10] == False):
     construct_row[1] += "SIGN-IN FAILED: Minor does not have signed waiver.<br/>"
   temp_output_df.append(construct_row)
  #temp_output_df.append(['CHECKED IN','No problems with any users','','','','','','','','','',''])
  output_df = pd.DataFrame(temp_output_df,columns=["Overall Status","Explanation","Given Name","Family Name","AGA ID","When AGA Expires?","Amount Invoiced","Amount Paid (+Refund)","Amount Owed","Is Child?","Is Child Form Signed?","Is Already Checked In?"])
  if "PROBLEM" in output_df['Overall Status'].tolist():
   bgcolor = "<style>body{background-color: yellow}</style>"
  else:
   bgcolor = "<style>body{background-color: green}</style>"
   for att in all_atts:
    result = display_results("UPDATE attendees SET checked_in=True WHERE id=%s" % att)
  button = "<br/><a href='" + request.url + "&is_resync=true'>Resync AGA Member List</a><br/>Please note that AGA Member Resync may take 10-15 seconds<br/>"
  return bgcolor + basic_df.to_html(index=False) + "<br/><br/>" + output_df.to_html() +  "<br/><br/>" + button

@app.route('/testbasic')
def testbasic():
 year = request.args.get('year')
 results = display_results("SELECT id,email FROM attendees WHERE year=" + str(year))
 my_string = ""
 for my_dict in results:
  email_hash = get_email_hash(my_dict['id'],str(year),is_user=False)
  my_string += "https://sleepy-springs-94281.herokuapp.com/testadv?attendee_id=" + str(my_dict['id']) + "&year=" + year + "&hash=" + email_hash  + "<br/>"
 results = display_results("SELECT id,year FROM users WHERE year=" + str(year))
 for my_dict in results:
  email_hash = get_email_hash(my_dict['id'],str(year),is_user=True)
  my_string += "https://sleepy-springs-94281.herokuapp.com/testadv?user_id=" + str(my_dict['id']) + "&year=" + year + "&hash=" + email_hash + "<br/>"
 return my_string
 
@app.route('/table')
def table():
 year = request.args.get('year')
 results = display_results("SELECT id,year,understand_minor,minor_agreement_received FROM attendees WHERE understand_minor='t' AND year=" + str(year))
 my_string = ""
 for result in results:
  if result['minor_agreement_received'] == False:
   my_string += "https://sleepy-springs-94281.herokuapp.com/testadv?attendee_id=" + str(result['id']) + "&year=" + str(result['year']) + "<br/>"
 my_string += "<br/><br/>TRUE<br/><br/>"
 for result in results:
  if result['minor_agreement_received'] == True:
   my_string += "https://sleepy-springs-94281.herokuapp.com/testadv?attendee_id=" + str(result['id']) + "&year=" + str(result['year']) + "<br/>"
 return my_string

 return str(display_results("SELECT * FROM " + table + add_on + ";"))

def resync():
 response = requests.get("https://www.usgo.org/mm/tdlista.txt")
 orig_file = io.StringIO(response.text)
 text = [line.replace("\n","").split("\t") for line in orig_file.readlines()]
 df = pd.DataFrame(text, columns=["Name","agaid","memtype","rating","expiry","club","state","sigma","joined"])
 df['agaid'] = df['agaid'].astype("str")
 return df

if __name__ == '__main__':
 from flask_sqlalchemy import get_debug_queries
 app.run(host='0.0.0.0', debug=True)
