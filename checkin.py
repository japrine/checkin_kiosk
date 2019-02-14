from datetime import datetime, date
import time
from string import capwords
from flask import Flask, render_template, url_for, redirect, session, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, PasswordField
from wtforms.validators import DataRequired, Length
from subprocess import call
from waitress import serve  # WSGI Server
from secrets import token_hex  # for random file name

# Try to import camera module
try:
    import picamera
    camera_enable = True
except ImportError:
    camera_enable = False


app = Flask(__name__, static_url_path='')
app.config['SECRET_KEY'] = 'ead0ac499de0e4425666e5b094dd7a94'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
db = SQLAlchemy(app)

waiting_for = []
here_to = [('', 'Reason for visit:'),
           ('Have Appointment', 'I Have a Appointment'),
           ('Need Appointment', 'I Need a Appointment'),
           ('Have Question', 'I Have a Question'),
           ('Drop Off', 'To Drop Off Taxes'),
           ('Pick Up', 'To Pick Up Taxes')]
admin_password = 'mastertax2018'

# get pi camera setup if imported, if fails disable camera
if camera_enable:
    try:
        camera = picamera.PiCamera()
    except:
        camera_enable = False

if camera_enable:
    camera.resolution = (1024, 768)
    camera.framerate = 30
    time.sleep(2)
    ex = camera.exposure_speed
    camera.shutter_speed = ex
    camera.exposure_mode = 'off'
    g = camera.awb_gains
    camera.awb_mode = 'off'
    camera.awb_gains = g
    camera.iso = 800


def capture_image():
    file_name = '{}_{}.jpg'.format(datetime.now().strftime('%m-%d-%Y'), token_hex(5))
    camera.capture("/home/pi/checkin/camera/{}".format(file_name))
    # with picamera.PiCamera() as camera:
    #     camera.resolution = (1024, 768)
    #     camera.shutter_speed = ex
    #     camera.exposure_mode = 'off'
    #     camera.awb_mode = 'off'
    #     camera.awb_gains = g
    #     camera.iso = 800
    #     camera.capture("/home/pi/checkin/camera/{}".format(file_name))
    #     camera.close()
    return file_name


def set_waiting_for():
    waiting_for.clear()
    for c, i in enumerate(Agent.query.all()):
        waiting_for.append((i.name, i.display_name))


def set_db_defaults():
    default = Agent(name="", display_name="Im Here For:")
    first = Agent(name="Name", display_name="Full Name")
    db.session.add(default)
    db.session.add(first)
    db.session.commit()


def reset_database():
    db.drop_all()
    db.create_all()
    set_db_defaults()
    set_waiting_for()


# DB Classes
class Guest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(40), nullable=False)
    herefor = db.Column(db.String(30), nullable=False)
    hereto = db.Column(db.String(30), nullable=False)
    indate = db.Column(db.DateTime, nullable=False, default=datetime.now)
    seen = db.Column(db.Boolean, nullable=False, default=False)
    image_file = db.Column(db.String(30), nullable=False, default='default.jpg')


class Agent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), nullable=False)
    display_name = db.Column(db.String(30), nullable=False)


# Flask Forms
class CheckInForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(min=3, max=38)])
    here_for = SelectField('Here to see', choices=waiting_for, validators=[DataRequired()])
    here_to = SelectField('Appointment', choices=here_to, validators=[DataRequired()])
    submit = SubmitField('Submit')


class SearchForm(FlaskForm):
    search = StringField('Search', validators=[DataRequired(), Length(min=3, max=25)])
    submit = SubmitField('Search')


class AgentForm(FlaskForm):
    name = StringField('Short Name', validators=[DataRequired(), Length(min=3, max=28)])
    display_name = StringField('Full Name', validators=[DataRequired(), Length(min=3, max=28)])
    submit = SubmitField('Save')


class AdminAccess(FlaskForm):
    password = PasswordField('Password')
    submit = SubmitField('Confirm')


# Flask Routes
@app.route("/checkin", methods=['GET', 'POST'])
def check_in():
    form = CheckInForm()
    if form.validate_on_submit():
        guest = Guest(name=capwords(form.name.data), herefor=form.here_for.data, hereto=form.here_to.data)
        db.session.add(guest)
        db.session.commit()
        return redirect(url_for('confirm'))
    return render_template('check-in.html', title='Check In', form=form)


@app.route("/confirm")
def confirm():
    last_guest = Guest.query.order_by(Guest.indate.desc()).first()
    if camera_enable:
        last_guest.image_file = capture_image()
        db.session.commit()
    return render_template('confirm.html', title='Confirmation', guest=last_guest)


@app.route("/", methods=['GET', 'POST'])
def guests():
    today = datetime.strptime(date.today().strftime('%Y, %m, %d'), '%Y, %m, %d')
    title = 'Today ' + today.strftime('%A, %m-%d-%Y')
    guest_list = Guest.query.order_by(Guest.indate.desc()).filter(Guest.indate >= today).all()
    form = SearchForm()
    if form.validate_on_submit():
        session['search'] = form.search.data
        return redirect(url_for('guests_search'))
    return render_template('guests.html', title=title, guests=guest_list,
                           form=form, title2="Guest List", if_pic=camera_enable)


@app.route("/toggle_guest/<int:guest_id>/<int:toggle>")
def toggle_guest(guest_id, toggle):
    guest = Guest.query.get_or_404(guest_id)
    if toggle is 1:
        guest.seen = True
    else:
        guest.seen = False
    db.session.commit()
    return redirect(url_for('guests'))


@app.route("/guests_search", methods=['GET', 'POST'])
def guests_search():
    name = session['search']
    title = 'Name Search - ' + name
    guest_list = Guest.query.order_by(Guest.indate.desc()).filter(Guest.name.like('%{}%'.format(name)))
    form = SearchForm()
    if form.validate_on_submit():
        session['search'] = form.search.data
        return redirect(url_for('guests_search'))
    return render_template('guest_search.html', title=title, guests=guest_list, form=form, title2="Back to Guest List")


@app.route("/settings", methods=['GET', 'POST'])
def settings():
    form1 = AdminAccess(prefix="form1")
    form2 = AdminAccess(prefix="form2")
    form3 = AdminAccess(prefix="form3")
    agents = Agent.query.order_by(Agent.id)
    if form1.validate_on_submit and form1.submit.data:
        # Reset All
        if form1.password.data == admin_password:
            reset_database()
            flash('Resetting Database!', 'success')
        else:
            flash('Wrong Password not resetting!', 'danger')
    if form2.validate_on_submit and form2.submit.data:
        # Power Off
        if form2.password.data == admin_password:
            call("sudo shutdown -h now", shell=True)
            flash('Shutting Down!', 'success')
        else:
            flash('Wrong Password not powering off!', 'danger')
    if form3.validate_on_submit and form3.submit.data:
        # Restart
        if form3.password.data == admin_password:
            call("sudo shutdown -r now", shell=True)
            flash('Restarting!', 'success')
        else:
            flash('Wrong Password not restarting!', 'danger')
    return render_template('settings.html', agents=agents, form1=form1, form2=form2, form3=form3)


@app.route("/edit_agent/<int:agent_id>", methods=['GET', 'POST'])
def edit_agent(agent_id):
    form = AgentForm()
    agent = Agent.query.get_or_404(agent_id)
    if form.validate_on_submit():
        agent.name = form.name.data
        agent.display_name = form.display_name.data
        db.session.commit()
        set_waiting_for()
        return redirect(url_for('settings'))
    form.name.data = agent.name
    form.display_name.data = agent.display_name
    return render_template('agent_settings.html', form=form)


@app.route("/new_agent", methods=['GET', 'POST'])
def add_agent():
    form = AgentForm()
    if form.validate_on_submit():
        agent = Agent(name=form.name.data, display_name=form.display_name.data)
        db.session.add(agent)
        db.session.commit()
        set_waiting_for()
        return redirect(url_for('settings'))
    return render_template('agent_settings.html', form=form)


@app.route("/delete_agent/<int:agent_id>", methods=['POST'])
def delete_agent(agent_id):
    agent = Agent.query.get_or_404(agent_id)
    db.session.delete(agent)
    db.session.commit()
    set_waiting_for()
    return redirect(url_for('settings'))


@app.route("/camera_img/<picture>")
def camera_img(picture):
    return send_from_directory('camera', picture)


if __name__ == '__main__':
    if not Agent.query.first():
        set_db_defaults()
    set_waiting_for()
    # app.run(host='0.0.0.0', port='5889', debug=False)  # for running with flask
    serve(app, host='0.0.0.0', port=80)
