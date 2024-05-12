import subprocess
import time
from datetime import datetime, timedelta, timezone
import importlib
import json
import sys, os
from datetime import datetime, timedelta, timezone
sys.path.append(os.path.abspath("../helperFiles"))
from sqlConnector import MySQLConnection 

try:
    import mysql.connector
except ImportError:
    print("\033[91mmysql.connector is not installed. Run 'pip install mysql-connector-python' \033[0m")



class OuterLayer():
    def __init__(self) -> None:
        self.database = MySQLConnection(host='localhost', user='Hybrid_IDPS', password='css2', database='hybrid_idps')
        self.database.setVerbose(False)
        self.database.hazmat_wipe_Table('outerLayerThreats')
        self.remove_firewall_rules()
        self.devices = {}
        self.ban_threshold = 1
        self.threatTable = {
            "Port Scanning": 0.3,
            "Flood Attack": 1,
            "SSH Brute Force Attack": 1,
            "Unusual Incoming Traffic": 0.1,
            "Unusual Outgoing Traffic": 0.1,
            "Suspicious Port Activity": 0.1,
            "SSH login":                0.3,
            "Possibly Bot Army":        0.4,
            "Possible Phishing":        0.4,
        }

        self.ipBanList = []
        self.locationBanList = [
            "Prague",
            "Minsk",
            "New Zealand",
            "North Korea",
            "Romania"
        ]

        self.incomingIpList = []
        self.count = 0

        self.central_analyzer()
        

    def central_analyzer(self):
        interval = 1
        start_time = time.time()
        while True:
            if time.time() - start_time >= interval:
                self.database.connect()
                self.add_devices()
                ###### Analyzer Functions ######

                self.track_incoming_traffic_ip()
                
                self.analyze_port_scanning()
                
                self.analyze_flood()

                self.analyze_ssh_brute_force()
                
                self.analyze_unusual_incoming_geolocation()

                self.analyze_unusual_outgoing_geolocation()

                self.analyze_ssh_logins()
                
                self.analyze_Websocket_Detection()

                self.analyze_BotNet()

                ###### Analyzer Functions ######
                
                self.ipBanList = self.database.get_banned_ips(self.ban_threshold) + self.database.get_Hybrid_Ban_IPs_DB(self.ban_threshold)
                print(self.ipBanList)
                self.display_Events_and_calc_threat_level()
                
                # self.database.get_banned_ips(self.ban_threshold)
                
                self.generate_firewall_rules(self.ipBanList)
                
                start_time = time.time()
                self.database.disconnect()
                

    def track_incoming_traffic_ip(self):
        self.count += 1
        if self.count == 100:
            self.incomingIpList = []
            self.count = 0
        event_types = ['Incoming TCP Traffic', 'Incoming UDP Traffic', 'Incoming ICMP Ping']
        self.incomingIpList = []
        for event_type in event_types:
            results = self.database.execute_query("SELECT DISTINCT ip_address FROM hybrid_idps.outerLayer WHERE event_type = %s AND processed = False", (event_type,))
            ips = [result['ip_address'] for result in results]
            self.incomingIpList.extend(ips)
        self.incomingIpList = list(set(self.incomingIpList))
        # print(f"Incoming IP List: {self.incomingIpList}")


    def analyze_event_type(self, event_type, threat_name, threshold):
        results = self.database.execute_query(f"SELECT * FROM hybrid_idps.outerLayer WHERE event_type = %s AND processed = False ORDER BY timestamp DESC", (event_type,))
        results = self.extract_ips(results)
        for ip, all_events in results.items():
            count = 0
            for event in all_events:
                count += 1
                if count > threshold:
                    log_name = f"{threat_name}-{event['timestamp']}"
                    self.add_threat(ip, log_name, event['geolocation'], event['timestamp'], threat_name)
                    count = 0
                self.database.execute_query(f"UPDATE hybrid_idps.outerLayer SET processed = True WHERE id = %s", (event['id'],))


    def analyze_port_scanning(self):
        event_type = 'Possible Port Scanning'
        threat_name = "Port Scanning"
        threshold = 100
        self.analyze_event_type(event_type, threat_name, threshold)


    def analyze_flood(self):
        event_types = ['Possible SYN Flood', 'Possible ACK Flood', 'Possible RST Flood', 'Possible FIN Flood', 'Possible UDP Flood', 'Possible ICMP Flood']
        threat_name = "Flood Attack"
        threshold = 10000
        for event_type in event_types:
            self.analyze_event_type(event_type, threat_name, threshold)


    def analyze_ssh_brute_force(self):
        event_type = 'Possible SSH Brute Force'
        threat_name = "SSH Brute Force Attack"
        threshold = 5
        self.analyze_event_type(event_type, threat_name, threshold)


    def analyze_unusual_incoming_geolocation(self):
        event_types = ['Incoming TCP Traffic', 'Incoming UDP Traffic', 'Suspicious Port Activity', 'Incoming ICMP Ping']
        threatName = "Unusual Incoming Traffic"
        
        # Define your threshold for determining what constitutes unusual traffic
        threshold = 5  # Placeholder threshold, adjust as needed
        
        for event_type in event_types:
            results = self.database.execute_query(f"SELECT * FROM hybrid_idps.outerLayer WHERE event_type = %s AND processed = False ORDER BY timestamp DESC", (event_type,))
            results = self.extract_ips(results)

            for ip, all_events in results.items():
                count = 0
                for event in all_events:
                    count += 1

                    # Check if the geolocation is in the list of unusual geolocations
                    if event['geolocation'] in self.locationBanList:
                        if count > threshold:
                            logName = f"{threatName}-{event['timestamp']}"
                            self.add_threat(ip, logName, event['geolocation'], event['timestamp'], threatName)
                            count = 0
                        self.database.execute_query(f"UPDATE hybrid_idps.outerLayer SET processed = True WHERE id = %s", (event['id'],))

    def analyze_unusual_outgoing_geolocation(self): 
        event_types = ['Outgoing TCP Traffic', 'Outgoing UDP Traffic', 'Outgoing ICMP Ping']
        threatName = "Unusual Outgoing Traffic"
        
        # Define your threshold for determining what constitutes unusual traffic
        threshold = 5  # Placeholder threshold, adjust as needed
        
        for event_type in event_types:
            results = self.database.execute_query(f"SELECT * FROM hybrid_idps.outerLayer WHERE event_type = %s AND processed = False ORDER BY timestamp DESC", (event_type,))
            results = self.extract_ips(results)
           
            for ip, all_events in results.items():
                count = 0
                for event in all_events:
                    count += 1

                    # Check if the geolocation is in the list of unusual geolocations
                    if event['geolocation'] in self.locationBanList or event['ip_address'] not in self.incomingIpList:
                        if count > threshold:
                            logName = f"{threatName}-{event['timestamp']}"
                            self.add_threat(ip, logName, event['geolocation'], event['timestamp'], threatName)
                            count = 0
                        self.database.execute_query(f"UPDATE hybrid_idps.outerLayer SET processed = True WHERE id = %s", (event['id'],))
    
    def analyze_ssh_logins(self):
        event_types = ['SSH Login Initiated']
        threatName = 'SSH login'
        threshold = 1

        # results = self.database.execute_query("SELECT * FROM hybrid_idps.outerLayer WHERE event_type ='SSH Login Initiated' ORDER BY timestamp DESC" )
        # results = self.extract_ips(results)
        for event_type in event_types:
            
            results = self.database.execute_query(f"SELECT * FROM hybrid_idps.outerLayer WHERE event_type = '{event_type}' AND processed = False ORDER BY timestamp DESC")
            results = self.extract_ips(results)
            for ip, all_events in results.items():
                
                count = 0
                for event in all_events:
                    count += 1
                    
                    # Check if the geolocation is in the list of unusual geolocations
                    if event['geolocation'] in self.locationBanList:
                            # print("entered if")
                            logName = f"{threatName}-{event['timestamp']}"
                            self.add_threat(ip, logName, event['geolocation'], event['timestamp'], threatName)
                            count = 0
                            # print('added threat')
                        
                    self.database.execute_query(f"UPDATE hybrid_idps.outerLayer SET processed = True WHERE ip_address = '{ip}' AND event_type = '{event_type}'")

    def analyze_Websocket_Detection(self):
        event_type = 'Possible Phishing'
        threatName = "Possible Phishing"
        
        # Define your threshold for determining what constitutes unusual traffic
        
        results = self.database.execute_query(f"SELECT * FROM hybrid_idps.outerLayer WHERE event_type = '{event_type}' AND processed = False ORDER BY timestamp DESC")
        #dest_ip = self.database.execute_query(f"SELECT dest_ip_address FROM hybrid_idps.outerLayer WHere event_type '{event_type}' AND processed = False ORDER BY timestamp DESC")
        results = self.extract_ips(results)
        
        for ip, all_events in results.items():
            for event in all_events:
                logName = f"{threatName}-{event['timestamp']}"
                self.add_threat(ip, logName, event['geolocation'], event['timestamp'], threatName)
            
            self.database.execute_query(f"UPDATE hybrid_idps.outerLayer SET processed = True WHERE ip_address = '{ip}' AND event_type = '{event_type}'")
    

    def analyze_BotNet(self):
            event_type = 'WebSocket Connection'
            threatName = "Possibly Bot Army"
            threshold = 2

            results = self.database.execute_query(f"SELECT ip_address, geolocation FROM hybrid_idps.outerLayer WHERE event_type = '{event_type}' AND timestamp >= NOW() - INTERVAL 5 SECOND AND processed = False ORDER BY timestamp DESC")

            result_dict = {}

            for result in results:
                geolocation = result['geolocation']
                if geolocation in result_dict:
                    result_dict[geolocation].append(result)
                else:
                    result_dict[geolocation] = [result]

            thresholded_locations = {key: [x['ip_address'] for x in value] for key, value in result_dict.items() if len(value) >= threshold} #The keys of 

            if len(thresholded_locations) > 0:
                
                for key in thresholded_locations:
                    print(thresholded_locations[key][0])
                    self.add_threat(thresholded_locations[key][0], f"Bots-{datetime.now(timezone.utc)}", key, datetime.now(timezone.utc), threatName)
                    #self.database.execute_query(f"UPDATE hybrid_idps.outerLayer SET processed = True WHERE ip_address = '{thresholded_locations[key][0]}' AND event_type = '{event_type}'")
            

    def analyze_BotNet(self):
        event_type = 'WebSocket Connection'
        threatName = "Possibly Bot Army"
        threshold = 2

        results = self.database.execute_query(f"SELECT ip_address, geolocation FROM hybrid_idps.outerLayer WHERE event_type = '{event_type}' AND timestamp >= NOW() - INTERVAL 5 SECOND AND processed = False ORDER BY timestamp DESC")

        result_dict = {}

        for result in results:
            geolocation = result['geolocation']
            if geolocation in result_dict:
                result_dict[geolocation].append(result)
            else:
                result_dict[geolocation] = [result]

        thresholded_locations = {key: [x['ip_address'] for x in value] for key, value in result_dict.items() if len(value) >= threshold} #The keys of 

        if len(thresholded_locations) > 0:
            
            for key in thresholded_locations:
                print(thresholded_locations[key][0])
                self.add_threat(thresholded_locations[key][0], f"Bots-{datetime.now(timezone.utc)}", key, datetime.now(timezone.utc), threatName)
                self.database.execute_query(f"UPDATE hybrid_idps.outerLayer SET processed = True WHERE ip_address = '{thresholded_locations[key][0]}' AND event_type = '{event_type}'")

# thresholded_values: [[{'ip_address': '192.168.1.78', 'geolocation': 'New Zealand', 'timestamp': datetime.datetime(2024, 5, 12, 2, 0, 37)}, {'ip_address': '192.168.1.78', 'geolocation': 'New Zealand', 'timestamp': datetime.datetime(2024, 5, 12, 2, 0, 37)}, {'ip_address': '192.168.1.78', 'geolocation': 'New Zealand', 'timestamp': datetime.datetime(2024, 5, 12, 2, 0, 36)}]]

    # def display_Events_and_calc_threat_level(self):
    #     for ip, deviceData in self.devices.items():
    #         print("\n")
    #         print(f"IP: {ip}")
    #         logs = deviceData["logs"]
    #         threatLevel = 0
    #         for threatName, threadType in logs.items():
    #             print(f"        {threatName}")
    #             threatLevel += self.threatTable[threadType]
                
    #         if threatLevel > 1: threatLevel = 1
    #         self.set_threat_level(ip, threatLevel)
    #         color_code = "\033[92m"  # Green
            
    #         if 0 < threatLevel < 0.5:
    #             color_code = "\033[93m"  # Yellow
    #         elif threatLevel >= 0.5:
    #             color_code = "\033[91m"  # Red
                
    #         reset_color = "\033[0m"
    #         print(f"    {color_code}[Threat Level]:   {threatLevel} {reset_color}")
        
    def display_Events_and_calc_threat_level(self):
        sorted_devices = sorted(self.devices.items(), key=lambda x: self.calculate_total_threat_level(x[1]))
        
        for ip, deviceData in sorted_devices:
            print("\n")
            print(f"IP: {ip}")
            logs = deviceData["logs"]
            threatLevel = 0
            for threatName, threadType in logs.items():
                print(f"        {threatName}")
                threatLevel += self.threatTable[threadType]
            
            if threatLevel > 1:
                threatLevel = 1
            self.set_threat_level(ip, threatLevel)
            color_code = "\033[92m"  # Green
            
            if 0 < threatLevel < 0.5:
                color_code = "\033[93m"  # Yellow
            elif threatLevel >= 0.5:
                color_code = "\033[91m"  # Red
                
            reset_color = "\033[0m"
            print(f"    {color_code}[Threat Level]:   {threatLevel} {reset_color}")

    def calculate_total_threat_level(self, deviceData):
        logs = deviceData["logs"]
        threatLevel = 0
        for threadType in logs.values():
            threatLevel += self.threatTable[threadType]
        return threatLevel


    def extract_ips(self, results):
        ip_dict = {}
        for entry in results:
            ip = entry['ip_address']
            if ip not in ip_dict:
                ip_dict[ip] = []
            ip_dict[ip].append(entry)
        return ip_dict

    def add_devices(self):
        results = self.database.execute_query(f"SELECT DISTINCT ip_address from hybrid_idps.outerLayer")
        ip_addresses = [ip['ip_address'] for ip in results]
        for ip in ip_addresses:
            if ip not in self.devices:
                self.devices[ip] = {'threatLevel': 0, 'logs': {}}
                
    def add_threat(self, ip_address, logName, geolocation, timestamp, threatName):
        if ip_address in self.devices:
            device = self.devices[ip_address]
            threatLevel = self.threatTable[threatName]
            
            if logName not in device['logs']:
                device['logs'][logName] = threatName
                self.database.add_threat_to_outer_Layer_Threats_DB(ip_address, logName, geolocation, timestamp, threatName, threatLevel)
            
        else:
            print(f"Device with IP address {ip_address} does not exist.")
            
    def set_threat_level(self, ip_address, newThreatLevel):
        if ip_address in self.devices:
            device = self.devices[ip_address]['threatLevel'] = newThreatLevel
        else:
            print(f"Device with IP address {ip_address} does not exist.")

    def run_powershell_as_admin(self, command):
        # Create a subprocess with administrative privileges
        process = subprocess.Popen(['powershell.exe', '-Command', command], shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, error = process.communicate()
        # print(error)
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, command, output=output, stderr=error)
        return output.decode('utf-8')

    def generate_firewall_rules(self, banned_ips):
        existing_rules = self.get_existing_firewall_rules()  # Get existing firewall rules
        
        powershell_commands = []
        for ip in banned_ips:
            # Check if a rule for the IP already exists
            if not any(f"Block Snort Inbound {ip}" in rule or f"Block Snort Outbound {ip}" in rule for rule in existing_rules):
                # Create PowerShell commands to block inbound and outbound traffic from the banned IP
                powershell_commands.append(f'New-NetFirewallRule -DisplayName "Block Snort Inbound {ip}" -Direction Inbound -LocalPort Any -Protocol Any -Action Block -RemoteAddress {ip}')
                powershell_commands.append(f'New-NetFirewallRule -DisplayName "Block Snort Outbound {ip}" -Direction Outbound -LocalPort Any -Protocol Any -Action Block -RemoteAddress {ip}')
            
        # Execute all PowerShell commands as administrator
        for cmd in powershell_commands:
            try:
                self.run_powershell_as_admin(cmd)
            except subprocess.CalledProcessError as e:
                print(f"Error executing PowerShell command: {e}")
                # Handle the error here, such as logging or displaying an error message to the user

    def get_existing_firewall_rules(self):
        # PowerShell command to get existing firewall rules with "Block Snort" in the display name
        try:
            # Run PowerShell command
            output = self.run_powershell_as_admin("Get-NetFirewallRule | Where-Object { $_.DisplayName -like 'Block Snort*' } | Select-Object -ExpandProperty DisplayName")
            # Split the output by newline to get individual rule names
            existing_rule_names = output.strip().split('\n')
            return existing_rule_names
        except subprocess.CalledProcessError as e:
            print(f"Error executing PowerShell command: {e}")
            # Handle the error here, such as logging or displaying an error message to the user
            return []

    def remove_firewall_rules(self):
        try:
            # Remove all firewall rules with display names containing "Block Snort" as administrator
            self.run_powershell_as_admin("Remove-NetFirewallRule -DisplayName 'Block Snort*'")
            print("Firewall rules removed successfully.")
        except subprocess.CalledProcessError as e:
            print(f"Error removing firewall rules: {e}")
            # Handle the error here, such as logging or displaying an error message to the user


if __name__ == "__main__":
    x = OuterLayer()