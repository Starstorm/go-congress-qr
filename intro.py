from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
import os
import hashlib
import pandas as pd
from delorean import parse

app = Flask("intro")
DATABASE_DEFAULT = 'postgres://khcldsyzgxvrin:b51bfd22c549f378c286cd20547978566232396a832143100ef576fd167bd9b2@ec2-107-20-188-239.compute-1.amazonaws.com:5432/dbl3c7ninomm7r'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', DATABASE_DEFAULT)
db = SQLAlchemy(app)
font_size = "10"

with open("tdlista.txt","r") as my_file:
 text = [line.replace("\n","").split("\t") for line in my_file.readlines()]
 df = pd.DataFrame(text, columns=["Name","agaid","memtype","rating","expiry","club","state","sigma","joined"])
 df['agaid'] = df['agaid'].astype("str")

def get_email_hash(id, year, is_user=False):
 if not is_user:
  resp = display_results("SELECT email FROM attendees WHERE id=" + id + " AND year=" + str(year)  + ";")
 else:
  resp = display_results("SELECT email FROM users WHERE id=" + id + " AND year=" + str(year) + ";")
 if len(resp) == 1:
  email = resp[0]['email']
 else:
  return False
 hash_object = hashlib.sha1(email)
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

def get_atts_from_user(user_id, year):
 resp = display_results("SELECT id FROM attendees WHERE user_id=" + str(user_id) + " AND year=" + str(year) + ";")
 all_attendees = []
 for elem in resp:
  all_attendees.append(elem['id'])
 return all_attendees

def display_results(query):
 result = db.session.execute(query)
 db.session.commit()
 final_result = []
 for rowproxy in result:
  final_result.append(dict(rowproxy.items()))
 return final_result

def get_invoice_total(id, year, is_user=False):
 if not is_user:
  cur_user = get_user(id)
  if not cur_user:
   return False
 else:
  cur_user = id
 all_atts = get_atts_from_user(cur_user, year)
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

def get_paid_total(id, year, is_user=False):
 if not is_user:
  cur_user = get_user(id)
  if not cur_user:
   return False
 else:
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

def check_aga_member(id, year):
 aga_id = display_results("SELECT aga_id FROM attendees WHERE id=" + str(id) + " AND year=" + str(year) + ";")
 if len(aga_id) == 1:
  return aga_id[0]['aga_id']
 else:
  return False

def is_current_membership(df, aga_id):
 if not aga_id:
  no_aga_id = True
  return False
 else:
  member = df[(df['agaid'] == aga_id)]
  if len(member) == 0:
   aga_id_not_found = True
   return False
  else:
   db_datetime = parse(member['expiry'], dayfirst=False, yearfirst=False).datetime
   end_date = parse("July 26th, 2018").datetime
   if db_datetime < end_date:
    no_membership = True
    return False
 return True
  
def is_minor_good(id, year):
 results = display_results("SELECT understand_minor,minor_agreement_received FROM attendees WHERE id=" + str(id) + " AND year=" + str(year) + ";")
 if results[0]['understand_minor'] == True and results[0]['minor_agreement_received'] == False:
  return False
 return True
  
@app.route('/basic')
def basic():
 return "Hello World!!!"

@app.route("/testadv")
def testadv():
 attendee_id = request.args.get('attendee_id')
 user_id = request.args.get('user_id')
 year = request.args.get('year')
 email_hash = request.args.get('hash')
 aga_id_error = False
 minor_bad = False
 membership_notes = ""
 
 if user_id and year and is_int(user_id) and is_int(year) and not attendee_id:
  is_user = True
  id = user_id
  # Get all attendees associated with user
  all_atts = get_atts_from_user(id, year)
  # Check their memberships
  for att in all_atts:
   aga_id = check_aga_member(att, year)
   if not is_current_membership(df,aga_id):
    aga_id_error = True
   if not is_minor_good(att,year):
    minor_bad = True
	  
 elif attendee_id and year and is_int(attendee_id) and is_int(year) and not user_id:
  is_user = False
  id = attendee_id
  aga_id = check_aga_member(id, year)
  if not is_current_membership(df,aga_id):
   aga_id_error = True
  if not is_minor_good(id,year):
   minor_bad = True
 else:
  return "<style>body{background-color: red}</style>You're trying to break me! You didn't enter a valid attendee_id/user_id or you tried to enter both! Bad boy, you failed!"
 #if not email_hash:
  #return "FLAWED QR CODE!!!"
 #else:
  #site_hash = get_user_hash(id,year,is_user)
  #if not site_hash:
   #return "Could not get site hash!!"
  #elif email_hash != site_hash:
   #return "THE HASHES DON'T MATCH!!"
 all_paid = get_paid_total(id, year, is_user=is_user)
 
 if not all_paid and all_paid != 0:
  return "<style>body{background-color: red}</style>You're trying to break me! Bad boy, you failed!"
 # Combine comp and paid together
 user_paid = all_paid[0]/100 + all_paid[1]/100
 # Get refund
 user_refund = all_paid[2]/100
 invoice_total = get_invoice_total(id, year, is_user=is_user)
 if not invoice_total and invoice_total != 0:
  return "<style>body{background-color: red}</style>You're trying to break me! Bad boy, you failed!"
 else:
  invoice_total = invoice_total/100
 total_due = invoice_total - user_paid + user_refund
 base_yellow = '<style>body{background-color: yellow}</style>'
 format = ''
 if total_due <= 0 and aga_id_error == False and minor_bad == False:
  format = "<style>body{background-color: green}</style><font size=\"" + font_size + "\">All Paid Up!</font><br/>"
 if total_due > 0:
  format += "<font size=\"" + font_size + "\">SIGN-IN FAILED: Money is owed to the Congress</font><br/>"
 if aga_id_error:
  format += "<font size=\"" + font_size + "\">SIGN-IN FAILED: Could not find current AGA membership.</font><br/>"
 if minor_bad:
  format += "<font size=\"" + font_size + "\">SIGN-IN FAILED: Minor does not have signed waiver.</font><br/>"
 if 'style' not in format:
  format = base_yellow + format
 return format + "The user was invoiced: $" + str(invoice_total) + "<br/>The user paid/was comped: $" + str(user_paid) + "<br/>The user was refunded: $" + str(user_refund) + "<br/>Therefore, the user's final total owed is: $" + str(total_due)

@app.route('/testbasic')
def testbasic():
 year = request.args.get('year')
 results = display_results("SELECT id,year FROM attendees WHERE year=" + str(year))
 my_string = ""
 for my_dict in results:
  my_string += "https://sleepy-springs-94281.herokuapp.com/testadv?attendee_id=" + str(my_dict['id']) + "&year=" + str(my_dict['year'])  + "<br/>"
 results = display_results("SELECT id,year FROM users WHERE year=" + str(year))
 for my_dict in results:
  my_string += "https://sleepy-springs-94281.herokuapp.com/testadv?user_id=" + str(my_dict['id']) + "&year=" + str(my_dict['year']) + "<br/>"
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

if __name__ == '__main__':
 from flask_sqlalchemy import get_debug_queries
 app.run(host='0.0.0.0', debug=True)
