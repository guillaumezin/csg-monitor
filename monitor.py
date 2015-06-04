#!/usr/bin/env python
# many ideas stolen from
# https://github.com/kylemarkwilliams/website-monitor

import requests
import smtplib
import time
import thread
import pibrella
import socket
import os.path
import math 

from datetime import datetime
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText

from repeattimer import RepeatTimer

from monitor_config import monitor_config
from servers import server_list

args = []
kwargs = {}


def mail(to, subject, text):
    msg = MIMEMultipart()
    msg['From'] = monitor_config['mail_user']
    msg['To'] = to
    msg['Subject'] = subject
    msg.attach(MIMEText(text))
    mailServer = smtplib.SMTP(monitor_config['mail_server'],
                              monitor_config['mail_server_port'])
    mailServer.ehlo()
    mailServer.starttls()
    mailServer.ehlo()
    mailServer.login(monitor_config['mail_user'], monitor_config['mail_pass'])
    mailServer.sendmail(monitor_config['mail_user'], to, msg.as_string())
    mailServer.close()


class Monitor(object):

    def __init__(self, server_list, monitor_config):
        print ("__init__")
        self.interval = monitor_config['interval']
        self.recipients = monitor_config['recipients']
        self.servers = self.get_servers(server_list)
	self.heartbeatFile = monitor_config['heartbeatFile']
	self.heartbeatHours = monitor_config['heartbeatHours']

	self.repeat_timer = RepeatTimer(self.interval,
                                   self.check_servers,
                                   *args,
                                   **kwargs)

        self.learn_ip()
        pibrella.button.pressed(self.btnPress)
        self.heartbeat()

    def learn_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("gmail.com",80))
        ip = s.getsockname()[0]
        s.close()
        for recipient in self.recipients:
            mail(recipient, 'Pi Monitor Started Successfully','Pi Monitor initialized on ip: %s' % (ip))

    def run(self):
        print ("run: ")
        self.repeat_timer.start()

    def check_servers(self, *args, **kwargs):
        """"""
        print ("check_servers: ")
	self.heartbeat()
        for server in self.servers:
            print (server.name)
            thread.start_new_thread(server.check_status, ())
        # email message about down servers
        time.sleep(5)
        down_servers = self.get_down_servers()
        if len(down_servers) > 0:
            self.send_down_servers_email(down_servers)
        else:
            self.reset()

    def get_down_servers(self):
        down_servers = []
        for server in self.servers:
            if server.status != 'OK' and server.fails >= server.max_fails and server.notified_fail == False:
                down_servers.append(server)
        return down_servers

    def send_down_servers_email(self, down_servers):
        self.alarm()
        print ("send_down_servers_email")
        message = ''
        for server in down_servers:
            text = "%s %s %s - %s\n" % (server.name,
                                        server.last_checked,
                                        server.url,
                                        server.status)
            message += text
            server.notified_fail = True
        for recipient in self.recipients:
            mail(recipient, 'Pi Monitor', message)

    def get_servers(self, server_list):
        """takes list of dicts and return list of Server objects"""
        print ("get_servers: ")
        servers = []
        for server in server_list:
            servers.append(Server(name=server['name'],
                                  url=server['url'],
                                  timeout=server['timeout'],
                                  max_fails=server['max_fails'],
                                  assert_string=server['assert_string']))
        return servers

    def btnPress(self,pin):
        self.reset()
        for server in self.servers:
            server.notified_fail = False
            server.fails = 0
            server.status = 'OK'
            server.assert_pass = True

    def reset(self):
        pibrella.light.stop()
        pibrella.buzzer.stop()

    def alarm(pin):
        pibrella.light.pulse()
        pibrella.buzzer.buzz(50)

    def heartbeat(self):
    	filePath = self.heartbeatFile
    	if(os.path.isfile(filePath)):
    	    f = open(filePath,"r")
    	    last = f.readline()
            f.close()
    	    print(last)
            dt_last = datetime.strptime(last, '%b %d %Y %I:%M%p')
            hours = math.floor(((datetime.now() - dt_last).total_seconds()) / 3600)
            print(hours)
            if(hours > self.heartbeatHours):
                for recipient in self.recipients:
                    mail(recipient, 'Pi Monitor Still Running','Pi Monitor still running fine')
                    self.writeHeartbeat()
    	else:
    	    self.writeHeartbeat()
	
    def writeHeartbeat(self):
        filePath = self.heartbeatFile
        f = open(filePath,"w")
        f.write(datetime.now().strftime('%b %d %Y %I:%M%p'))
        f.close()

class Server:

    def __init__(self, name, url, timeout, max_fails, assert_string):
        self.name = name
        self.url = url
        self.timeout = timeout
        self.max_fails = max_fails
        self.assert_string = assert_string

        self.fails = 0
        self.status_code = 0
        self.status = ''
        self.last_checked = datetime.min
        self.notified_fail = False
        self.assert_pass = False

    def check_status(self):

        self.last_checked = datetime.now()
        try:
            r = requests.get(self.url, timeout=self.timeout)

        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            self.status_code = 500
            self.status = str(e)
            self.fails += 1

        else:
            self.status_code = r.status_code
            if r.status_code == 200:
                if self.assert_string in r.text:
                    self.status = 'OK'
                    self.fails = 0
                    self.notified_fail = False
                    self.assert_pass = True
                else:
                    self.status = 'Assert Failed'
                    self.fails += 1
                    self.assert_pass = False
            else:
                self.fails += 1
                self.status = 'ERROR'

        print (self.name, self.status)
        return self

if __name__ == "__main__":
    # need to update server list when necessary
    monitor = Monitor(server_list, monitor_config)
    monitor.run()
    #end
