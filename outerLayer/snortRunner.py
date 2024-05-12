from datetime import datetime
import re
import subprocess
import os
import hashlib
import time
from threading import Thread
import traceback
import websocket
import json
import sys
import os, sys
sys.path.append(os.path.abspath("../helperFiles"))
from sqlConnector import MySQLConnection  
from wipeAlertFile import hazmat_wipe_alert_file
from ipGeoMapper import find_location, subdivide_ip_range
 

def list_interfaces(find_Interface_subString = None):
    # If you don't know what interface your running run this.
    snort_bin_path = r'C:\Snort\bin'
    try:
        os.chdir(snort_bin_path)
        
        result = subprocess.run('.\snort -W', shell=True, capture_output=True, text=True)

        if result.returncode == 0:
            interfaces = [line.strip() for line in result.stdout.split('\n') if line.strip()]

            foundInterface = None
            print("Interfaces:")
            for interface in interfaces:
                if (find_Interface_subString):
                    if find_Interface_subString in interface:
                        foundInterface = interface
                        pass
                print(interface)
                
            if foundInterface:
                print("\033[92m" + f"Found Interface. {foundInterface[0]} with substring {find_Interface_subString}" + "\033[0m")
                return int(foundInterface[0])
            else:
                print("\033[91m" + f"No Interface was found with Substring {find_Interface_subString}" + "\033[0m")
                sys.exit()
                
                
            return -1
        else:
            print(f'Error: {result.stderr}')
            return None

    except subprocess.CalledProcessError as e:
        print(f'Error: {e}')
        return None
    except Exception as e:
        print(f'Unexpected error: {e}')
        return None

def doesPathExist(filePath):
    return os.path.exists(filePath)

def checkDirectories(snort_Dirs):
    for dir_name, dir_path in snort_Dirs.items():
        if not doesPathExist(dir_path):
            print(f"\033[91m[ERROR] {dir_name} directory: {dir_path} does not exist.\033[0m")
            sys.exit()
        else:
            print(f"\033[92m[SUCCESS] {dir_name} directory exists.\033[0m")

def displayRules(local_rules_file_path):
    marker_count = 0
    marker_found = False

    try:
        with open(local_rules_file_path, 'r') as file:
            lines = [line.strip() for line in file]
            
            if len(lines) == 0:
                return False
            
            max_line_length = max(len(line) for line in lines)
            
            print("┌" + "─" * (max_line_length + 2) + "┐")  # Top of the box
            print(f"│ {file.name.center(max_line_length)} │")  # Header
            print("├" + "─" * (max_line_length + 2) + "┤")  # Separator
            
            for line in lines:
                if line.strip() == "#-------------":
                    marker_count += 1
                    if marker_count == 2:
                        marker_found = True
                        continue  # Skip printing the second marker line
            
                if marker_found:
                    print(f"│ {line}{' ' * (max_line_length - len(line))} │")  # Adjust spacing for each line
            
            print("└" + "─" * (max_line_length + 2) + "┘")  # Bottom of the box
    except FileNotFoundError:
        print(f"\033[91m[ERROR] {local_rules_file_path} does not exist.\033[0m")

def CalculateThreatLevel():
    return 0

def runSnort(snort_Dirs, interface_Number):
    snort_bin_path = snort_Dirs['Bin Directory']
    snort_config_path = snort_Dirs['Snort Configuration File']
    snort_command = fr'.\snort -i {interface_Number} -c {snort_config_path} -A full -k none'
    full_snort_path = os.path.join(snort_bin_path, 'snort.exe')  # Assuming the executable is named snort.exe
    # runas_command = fr'runas /user:Administrator "{snort_command}"'
    runas_command = fr'{snort_command}'
    try:
        print("\033[93m" + f'Executing Snort Command: {runas_command}' + "\033[0m")       
        print("  - You may be asked to enter your admin-password, in a new cmd window. Do it. ")
        os.chdir(snort_bin_path)
        subprocess.Popen(runas_command, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.DETACHED_PROCESS)
    except Exception as e:
        print(f'Unexpected error: {e}')

def check_file_changes(file_path, file_Check_Interval, displayAlerts, mySqlConnection):

    print("file starts")
    
    extracted_data = {}

    try:
        with open(file_path, 'rb') as file:
            current_hash = hashlib.sha256(file.read()).hexdigest()
    except FileNotFoundError:
        print(f"File not found: {file_path}")
        return

    read_Up_To = 0

    while True:
        try:
            with open(file_path, 'rb') as file:
                new_hash = hashlib.sha256(file.read()).hexdigest()

            if new_hash != current_hash:
                if displayAlerts:
                    print(f"File contents changed in {file_path}. New contents:")
                with open(file_path, 'r') as file:
                    fileData = file.read()
                    print(fileData[:-7])
                    newSnortAlerts, read_Up_To = handle_Snort_Alerts(displayAlerts, fileData, read_Up_To) #Reads only the updating part of the file. 
                    #Sending Data to server
                    if displayAlerts:
                        for alert in newSnortAlerts:
                            (src_ip, geolocation, dateTime, alertName, threat_level, src_port, dest_port, protocol, ) = alert
                            print(f"Source IP: {src_ip}, Geolocation: {geolocation}, Date/Time: {dateTime}, Alert Name: {alertName}, Threat Level: {threat_level}, Source Port: {src_port}, Destination Port: {dest_port}, Protocol: {protocol}")

                            
                    mySqlConnection.add_data_to_outer_layer_bulk(newSnortAlerts)
                    # mySqlConnection.add_data_to_outer_layer(ip_address, geolocation, event_type, threat_level, source_port, destination_port, protocol, payload)
              
                    current_hash = new_hash
        except FileNotFoundError:
            print(f"File not found: {file_path}")
            return

        time.sleep(file_Check_Interval)  

def get_Alert_ID_and_Name(alertLine):
    # Define the pattern to match the desired information
    pattern = r'\[([0-9]+:[0-9]+:[0-9]+)\]\s*([\w\s]+)\s*\[\*\*\]'

    # Use re.search to find the first match in the string
    match = re.search(pattern, alertLine)

    # Check if a match is found
    if match:
        # Extract the captured groups from the match
        number = match.group(1)
        text = match.group(2)
        return number, text.strip()  # Remove leading and trailing whitespaces from the text
    else:
        return None, None  # Return None if no match is found

def get_ip_and_time_line(ip_and_time_line):
    dateTime, src_ip, _,  dest_ip = ip_and_time_line.split()
    # date, time = dateTime.split('-')
    return dateTime, src_ip, dest_ip

def get_protocol(protocol_Line):
    parts = protocol_Line.split()
    if len(parts) == 6:
        protocol, ttl, tos, id, ip_len, dgm_len, = parts
    else:
        protocol, ttl, tos, id, ip_len, dgm_len, df = parts 
    return protocol

def dateTime_to_ISO(dateTimeString):
    current_year = datetime.now().year
    combined_string = f'{current_year}/{dateTimeString}'
    parsed_datetime = datetime.strptime(combined_string, '%Y/%m/%d-%H:%M:%S.%f')
    iso_date = parsed_datetime.isoformat()
    return iso_date

def handle_Snort_Alerts(displayAlerts, fileData, read_Up_To):
    newSnortAlerts = []

    entries = fileData.split('\n\n')

    entries = entries[read_Up_To:]

    for entry in entries:
        lines = entry.split('\n')
        lines = [line for line in lines if line.strip()]
        if (len(lines) > 3):
            # [**] [1:1000001:0] TEsting ICMp alert [**]
            alertLine = lines[0]
            ip_and_time_Line   = lines[2]
            protocol_Line = lines[3]
            try:
                alertId, alertName = get_Alert_ID_and_Name(alertLine)
                
                if (not alertId or not alertName):
                    continue
                
                dateTime, src_ip, dest_ip = get_ip_and_time_line(ip_and_time_Line)
                
                if alertName == "Outgoing TCP Traffic" or alertName == "Outgoing UDP Traffic" or alertName == "Outgoing ICMP Ping" or alertName == "Possible Phishing" or alertName == "WebSocket Connection":
                    # Swap src_ip and dest_ip
                    src_ip, dest_ip = dest_ip, src_ip
              
                isoDateTime = dateTime_to_ISO(dateTime)

                protocol = get_protocol(protocol_Line)

                if (protocol == "ICMP" or protocol == "IPV6-ICMP"):
                    src_port = None
                    dest_port = None
                else:
                    index = src_ip.rfind(":")  # Extract source port from the IP address
                    src_port = src_ip[index+1:]
                    src_ip = src_ip[:index]

                    index = dest_ip.rfind(":")  # Extract destination port from the IP address
                    dest_port = dest_ip[index+1:]
                    dest_ip = dest_ip[:index]

                # dataLine = {'src_ip': src_ip, 'dest_ip': dest_ip, 'dateTime': dateTime, 'alertId': alertId, 'alertName' : alertName}
                # ip_address, geolocation, event_type, threat_level, dateTime

                geolocation = find_location(src_ip)

                threat_level = CalculateThreatLevel() #Always 0 Need to Complete.
                dataLine = (src_ip, geolocation, isoDateTime, alertName, threat_level, src_port, dest_port, protocol)

                
                newSnortAlerts.append(dataLine)
                
                
            except Exception as E :
                print(f"Error at handle_Snort_Alerts {E} with string {alertLine} and entry \n {entry}")
                traceback.print_exc()
                time.sleep(10)

    read_Up_To += len(entries) - 1

    return newSnortAlerts, read_Up_To

def filePrefix():
    script_location = os.path.realpath(__file__)
    HybridIDPS_index = script_location.rfind("HybridIDPS") + len('HybridIDPS') 
    
    for idx in range(HybridIDPS_index, len(script_location)):
        if script_location[idx] == "\\":
            HybridIDPS_index = idx
            break
         
    # if any(char.isspace() for char in script_location):
    #     print("\033[31mTHERE CAN BE NO SPACES IN FILE PATH.\033[0m")
    #     print(script_location)
    #     space_index = script_location.index(' ')
    #     print(' ' * space_index + '^')
    #     sys.exit()
    
    return fr"{script_location[:HybridIDPS_index]}"

def overwrite_snort_local_rules():
    try:
        with open(snort_Dirs['Local Rules File'], 'r') as f:
            local_rules_content = f.read()

        with open(snort_Dirs['Snort Local Rules File'], 'w') as f:
            f.write(local_rules_content)

        print("Snort local rules file overwritten successfully with HybridIDPS local.rules")
    except FileNotFoundError:
        print("File not found. Check the file paths.")
    except Exception as e:
        print("An error occurred:", e)

if __name__ == '__main__':
    # This file will save snort alerts to a database #
    snort_Dirs = {
        'Snort Directory':          r'C:\Snort',
        'Log Directory':            r'C:\Snort\log',
        'Rules Directory':          r'C:\Snort\rules',
        'Local Rules File':         fr'{filePrefix()}\snortFiles\localRule\local.rules',
        'Snort Local Rules File':   r'C:\Snort\rules\local.rules',
        'Bin Directory':            r'C:\Snort\bin',
        'Etc Directory':            r'C:\Snort\etc',
        'Alert File':               fr'C:\Snort\log\alert.ids',
        'Snort Configuration File': r'c:\Snort\etc\snort.conf',
    }
    
    
    
    mySqlConnection = MySQLConnection()
    mySqlConnection.hazmat_wipe_Table('outerLayer')
    hazmat_wipe_alert_file(snort_Dirs['Alert File'])
    displayAlerts = True
    
    checkDirectories(snort_Dirs)
    overwrite_snort_local_rules()
    file_Check_Interval = 2 

    interface_Number = list_interfaces(find_Interface_subString = "VMnet8") # You may need to change this. When running the code, it will print ur interfaces. Add a substring from it to this.

    displayRules(snort_Dirs['Local Rules File'])
    runSnort(snort_Dirs, interface_Number=interface_Number)

    
    Thread(target = check_file_changes, args=(snort_Dirs['Alert File'], file_Check_Interval, displayAlerts, mySqlConnection)).start()   #Checks the alert.ids and sends updates to server.
