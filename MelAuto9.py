# For main documentation see the README.txt
# MelAuto is a wrapper program for MELCOR
# Erick Ball, ERI, 2016-2017

# To do:
# Round off times
# Record the calculation time when MELCOR starts and stops
# Fix the restart-copying, it always seems to fail
# Handle CVTNQE errors. Maybe go back and make the timestep bigger?

# Import system modules
import sys, string, os, signal, subprocess, threading, _thread, time, shutil, datetime
from subprocess import PIPE, CREATE_NEW_CONSOLE
        
        
def main_function():
    
    # This thread just sits around waiting for keyboard input, then sends that to the main loop.
    # The point is that the main loop can do other stuff in the meantime, like check on melcor's output.
    def input_thread(L):
        key = input()
        L.append(key)
        print(L[0])
        
    def get_restarts():
        restarts = []
        try:
            mes_file = open(message_file, 'r')
            messages = mes_file.readlines()
            mes_file.close()
        except:
            print("Error opening message file to read restarts.")
        for line in messages:
            if line.strip().startswith('Restart written'):
                restarts.append((float(line.split()[4]),int(line.split()[6])))
                if len(restarts) > 1:
                    rst = 0
                    while True:
                        if rst >= len(restarts)-1:
                            break
                        #print("\n" + str(len(restarts)) + " " + str(rst))
                        #print(restarts)
                        if restarts[rst][1] >= restarts[-1][1]:
                            #print("Deleting. " + str(restarts[rst]))
                            del restarts[rst]
                        else:
                            rst += 1
        return restarts
    
    

        
    # Main function:
    
    # Do some initial setup stuff:
    # find the directory in which this executable (and presumably the melcor executable) resides.
    exdirec = os.path.dirname(os.path.realpath(sys.argv[0]))
    
    # check the arguments
    if len(sys.argv) < 2:
        print("Specify the .cor file to use. Optional: specify cycle number to start at, time to start at (with decimal), or 'restarts' or 'r' to see all the possibilities.")
        sys.exit(1)
    if not sys.argv[1].endswith('.cor'):
        print("Invalid .cor file.")
        sys.exit(1)

    # Copy into a temporary .cor file, so there's no need to modify the original.
    corfile = sys.argv[1][:-4]+"_auto.cor"
    file_increment = 0
    while os.path.exists(corfile): # don't overwrite a previous temp file
        file_increment += 1
        corfile = sys.argv[1][:-4] + "_auto" + str(file_increment) + ".cor"
    try:
        shutil.copyfile(sys.argv[1], corfile)
    except:
        print("Unable to copy specified .cor file. Check if it's in the current directory.")
        sys.exit(1)
    
    # read in the .cor file for mods
    dotcor = open(corfile, 'r')
    melcor_input = dotcor.readlines() # read in the whole .cor file
    dotcor.close()

    # Dig through the .cor file to find the name of the message file
    for line in melcor_input:
        if line.strip().startswith('MESSAGEFILE') or line.strip().startswith('messagefile'): # tokenize, take the last word in the line, strip the first and last characters (the quotes)
            message_file = line.strip().split()[-1][:-1][1:]
            
    # Dig through the .cor file to find the name of the restart file
    for line in melcor_input:
        if line.strip().startswith("MEL_RESTARTFILE") or line.strip().startswith("mel_restartfile"): # tokenize, take the last word in the line, strip the first and last characters (the quotes)
            restartfile = line.strip().split()[-1][:-1][1:]
    
    # Get startcycle from args, run restarts mode if necessary
    startcycle = -2
    starttime = -1.e6
    if len(sys.argv) > 2:
        # Restarts mode: look through the .cor file to find the name of the message file
        # Then read through the message file to find all the restarts.
        if sys.argv[2] == 'restarts' or sys.argv[2] == 'r':
            print("Running in restarts mode. For a slower but possibly more accurate list, enter 2 as the argument instead.")
            print(message_file)
            # open .mes file, print any line starting with 'Restart written'
            restarts = get_restarts()
            for rest in restarts:
                print("Restart at " + str(rest[0]) + "\t seconds, cycle " + str(rest[1]))
            print(str(len(restarts)) + " restarts available.")
            os.remove(corfile)
            sys.exit(0)
        else:
            if '.' in sys.argv[2]:
                try: starttime = float(sys.argv[2])
                except: print("Invalid start time.")
            else:
                try: 
                    startcycle = int(sys.argv[2])
                    if startcycle >= 10000000:
                        print("Cycle number too high. Specify the time to start from instead.")
                        sys.exit(0)
                except: print("Invalid cycle number.")

    # Everything above here should not need to be done more than once.
    
    def run_melcor(automatic, auto_stop_time=[1.0e10]):
        # Handle ctrl-C by sending a terminate signal to melcor
        def signal_handler(signal, frame):
            print('You pressed Ctrl+C!')
            melcor.terminate()
            print("Terminated MELCOR.")
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler) # to make ctrl-C work
        dotcor = open(corfile, 'r')
        melcor_input = dotcor.readlines()
        dotcor.close()
        tend = -1.0e10
        
        for line_num in range(1,len(melcor_input)):
                line = melcor_input[line_num]
                # Check what the end time for this run is.
                if line.strip().startswith("EXEC_TEND") or line.strip().startswith("exec_tend"):
                    #print("Found end time.\n")
                    tend = float(line.split()[1].split('!')[0]) # Leave out any comment after the time
        if tend < -1.0e-9:
            print("Error. Couldn't find end time in .cor file.\n")
            sys.exit(1)
        #print(startcycle)
        # modify the .cor file to use the command-line-specified startcycle (or the cordbd fix one, or the auto-stop one)
        if startcycle != -2 or starttime != -1.e6: # Need to make sure that only one of these can be true.
            found_startcycle_line = False
            for line_num in range(0,len(melcor_input)):
                line = melcor_input[line_num]
                if line.strip().startswith("MEL_RESTARTFILE") or line.strip().startswith("mel_restartfile"):
                    restartfile = line.strip().split()[1]
                    if startcycle > -2:
                        melcor_input[line_num] = "MEL_RESTARTFILE " + restartfile + " NCYCLE " + str(startcycle) + "\n\n"
                    if starttime > -1.e6:
                        melcor_input[line_num] = "MEL_RESTARTFILE " + restartfile + " TIME " + str(starttime) + "\n\n"
                    if startcycle > -2 and starttime > -1.e6:
                        print("Error: Start time and start cycle are both specified.")
                    found_startcycle_line = True
            #print(melcor_input)
            if found_startcycle_line:
                dotcor = open(corfile, 'w') # just overwrite the whole file
                for line in melcor_input:
                    dotcor.write(line)
                # record the time dotcor was modified
                if startcycle > -2:
                    dotcor.write("\n! MelAuto changed startcycle to " + str(startcycle) + " at " + str(datetime.datetime.now()) + " as specified on command line (or automatically).")
                if starttime > -1.e6:
                    dotcor.write("\n! MelAuto changed start time to " + str(starttime) + " at " + str(datetime.datetime.now()) + " as specified on command line (or automatically).")
                dotcor.close()
                print("Modified .cor file at " + str(datetime.datetime.now()))
            else:
                print("Unable to modify start cycle (could not find line starting with MEL_RESTARTFILE in .cor)")
                sys.exit(1)
            if startcycle != -1 and startcycle != 2: # Using some restart that is not the most recent. This should work even if startcycle is -2 and starttime is some previous restart's time.
                if not auto: # why is this auto and not automatic? It works so I'm not going to mess with it, but it seems like it should be out of scope.
                    check = input("Are you sure you want to use an earlier restart? This can overwrite existing data. (y/n)")
                else:
                    check = 'y'
                if check == 'y' or check == 'Y' or check == 'yes' or check == 'Yes' or check == 'YES':
                    try:
                        shutil.copy(restartfile,'old_'+restartfile) # Save the restart file under a new name before overwriting. But only one. Don't want to end up with a bunch, they're big.
                    except:
                        print("Failed to copy restartfile.")
                else:
                    print("Aborting.")
                    sys.exit(1)
        else:
            print("Invalid start cycle or no start cycle specified. Using value from .cor.")
                    
        # Try to find the melcor executable
        melcors_found = 0
        melcor_exec = ""
        for file in os.listdir(exdirec):
            if file.startswith("Melcor"):
                if file.endswith(".exe"):
                    melcors_found += 1
                    melcor_exec = file
        if melcors_found == 0:
            print("No MELCOR executable found in this directory (the one where the wrapper executable is).")
        if melcors_found > 1:
            print("Found multiple MELCOR executables. Using the last one.")
        
        # Start up MELCOR
        command = exdirec + "\\" + melcor_exec + " " + corfile# + " N++=ON"
        if auto:
            command = command + " ow=e"
        print("Starting MELCOR with command " + command)
        melcor = subprocess.Popen(command, stdin=0, stdout=PIPE, stderr=PIPE)
        
        # Record time that calculation started
        start_time = datetime.datetime.now()
        dotcor = open(corfile, 'a') # append
        dotcor.write("\n! MELCOR calculation started at " + str(start_time) + " \n")
        print("\n! MELCOR calculation started at " + str(start_time) + " \n")
        dotcor.close()
        
        # if we're running MELCOR, we record that in the name of a text file
        if startcycle != 2:
            filenames = os.listdir()
            for increment in range(1,10000):
                name = "melauto_started_melcor_" + str(increment) + "_times"
                if name in filenames:
                    increment += 1
                    os.rename(name,"melauto_started_melcor_" + str(increment) + "_times")
                    break
            if increment >= 9999:
                with open("melauto_started_melcor_1_times", 'x') as touched_file:
                    pass
                    
        
        calc_time = None # calculation time
        cycle = None
        dt = None
        cputime = None
        
        calc_time0 = None
        cycle0 = None
        dt0 = None
        cputime0 = None
        start_flag = 0
        stopval = 0
        dtsmall = False
        dtsmall_limit = 3600*3 # after 3 hours of small timesteps, give up on getting anywhere
        dtsmall_cycle = False
        
        # This loop runs the whole time MELCOR is running
        while(melcor.poll() == None):
            time.sleep(.01)
            line = melcor.stdout.readline().decode().strip()
            if line:
                print(line)
                pieces = line.split()
                if pieces[0] == "CYCLE=":
                    negtime = 0
                    try:
                        calc_time = float(pieces[3])
                    except:
                        negtime = 1
                        calc_time = float(pieces[2][2:])
                    cycle = int(pieces[1])
                    try:
                        dt = float(pieces[5-negtime])
                    except:
                        try:
                            dt = float(pieces[6-negtime])
                        except:
                            print("Error reading dt.\n")
                    try:
                            cputime = float(pieces[7-negtime])
                    except:
                        try:
                            cputime = float(pieces[8-negtime])
                        except:
                            pass
                    if start_flag == 0:
                        calc_time0 = time
                        cycle0 = cycle
                        dt0 = dt
                        cputime0 = cputime
                        start_flag = 1
                    # auto-stop if desired
                if pieces[0] == "/SMESSAGE/":
                    calc_time = float(line[10:].strip()[5:].split()[0])
                if start_flag > 0:
                    if dt < 1.0e-5:
                        if dtsmall == False:
                            dtsmall = cputime # time it first got small
                            dtsmall_cycle = cycle
                        else:
                            if cputime - dtsmall > dtsmall_limit:
                                print("The timestep has stayed too small for too long.")
                                melcor.terminate()
                                stopval = dtsmall_cycle
                    else: # timestep is not small
                        dtsmall = False # reset the countup
                    if "stopcalc" in line: # this is a flag you can put in a control function message to stop the calculation.
                    #if "IRWST" in line: # for test purposes only
                        print("\nStop flag found in line.\n")#,calc_time,tend)
                        # print("prev_TEND is ",prev_TEND)
                        # print("calc_time is ",calc_time)
                        if calc_time < tend - 0.31: # Originall this was 0.11, but it turns out the message time can vary a bit.
                                auto_stop_time[0] = calc_time + 0.1 # Allow for rounding error, to make sure the message appears again 
                                                                    # before the end of the calculation.
                        # if "vacuum" in line: # for test purposes only
                        if "disable oxidation" in line:
                            # This change to the .cor actually has to be done when we get back to this point later, it shouldn't be done
                            # the first time we stop. So I moved it down into main()
                            #values = "COR_TST  0    0    0    1    0    0    0    0    0    0"
                            #set_COR_TST(values)
                            stopval = "COR_TST  0    0    0    1    0    0    0    0    0    0"
                    if calc_time >= auto_stop_time[0]:
                        melcor.terminate()
                        print("Stopping because auto-stop message was detected in MELCOR output. Time ", auto_stop_time[0])
                        # print("Copying restart file into auto_stop_" + restartfile + ".")
                        dotcor = open(corfile, 'a') # append
                        dotcor.write("\n! Stopping because auto-stop message was detected in MELCOR output. Time ", auto_stop_time[0], "\n")
                        # dotcor.write("Copying restart file into auto_stop_" + restartfile + ".\n")
                        # if "auto_stop_"+restartfile in os.listdir():
                            # print("Overwriting previous saved restart file.")
                            # dotcor.write("Overwriting previous saved restart file.")
                        # try:
                            # shutil.copy(restartfile,"auto_stop_" + restartfile)
                        # except:
                            # dotcor.write("Copy failed. \n")
                            # print("Copy failed.")
                        dotcor.close()
                        
            #print(melcor.stderr.readline().decode().strip())
            # For some reason printing stderr makes stdout not show up.
            
            #print(melcor.stderr.readline())
            # if auto:
                # L = []
                # _thread.start_new_thread(input_thread, (L,))
                # while True:
                    # time.sleep(.01)
                    # line = melcor.stdout.readline().decode().strip()
                    # print(line)
                    # if "{extend applies only to list files}" in line:
                        # melcor.stdin.write(bytes('e\n','utf-8'))
                        # melcor.stdin.flush()
                        # break
                # while not L:
                    # time.sleep(.01)
                    # print(melcor.stdout.readline().decode().strip())
                    # #print(melcor.stderr.readline().decode().strip())
                    # if melcor.poll() != None: break
                # # print(L)
                # if melcor.poll() != None: break 
                # print("\nHold down enter to stop execution.")
                # melcor.stdin.write(bytes("stop!\n",'utf-8'))
                # melcor.stdin.flush()
                # stopval = 1 # this will indicate to not restart the calculation
                # for i in range(0,300):
                    # time.sleep(0.01)
                    # line = melcor.stdout.readline().decode().strip()
                    # print(line)
                # # userinput = input("Keypress detected.\n")
                # # if melcor.poll() != None: break 
                # # print(userinput)
                # # #melcor.stdin.write(bytes("\x1B[A",'utf-8'))
                # # #melcor.stdin.flush()
        
            
                
        # Record time that calculation ended
        dotcor = open(corfile, 'a') # append
        dotcor.write("\n! MELCOR calculation ended at " + str(datetime.datetime.now()) + " \n\n\n\n")
        print("\n! MELCOR calculation ended at " + str(datetime.datetime.now()) + " \n")
        dotcor.close()
        dotcor = open(corfile, 'r')
        melcor_input = dotcor.readlines()
        dotcor.close()
        #print("Stopval is ",stopval)
        return stopval
    # Melcor is no longer running. End run_melcor().
        
        
        
        
        
        
    # Routines for making changes to the .cor file
        
    def set_COR_DTC(dtemp, step, iters):
        dotcor = open(corfile, 'r')
        melcor_input = dotcor.readlines()
        dotcor.close()
        # modify the .cor file to use a looser tolerance for COR_DTC sensitivity coefficient, in hopes of fixing CORDBD error
        found_cor_dtc_line = False
        for line_num in range(1,len(melcor_input)):
            line = melcor_input[line_num]
            if "END PROGRAM MELCOR" in line:
                melcor_input[line_num] = ""
            if line.strip().startswith("COR_DTC") or line.strip().startswith("cor_dtc"):
                melcor_input[line_num] = "!" + line
                found_cor_dtc_line = True
        #print(melcor_input)
        #if found_cor_dtc_line:
        dotcor = open(corfile, 'w') # just overwrite the whole file
        for line in melcor_input:
            dotcor.write(line)
        # record the time dotcor was modified
        #dotcor.write("\n! MelAuto changed cor_dtc to " + str(dtemp) + " " + str(step) + " " + str(iters) + " at " + str(datetime.datetime.now()) + " after CORDBD error.")
        dotcor.write("\nCOR_INPUT\n")
        dotcor.write("COR_DTC " + "{0:.7f}".format(dtemp) + " " + "{0:.7f}".format(step) + " " + str(iters) + " ! " + str(datetime.datetime.now()) +  "\n")
        dotcor.write("\nEND PROGRAM MELCOR")
        dotcor.close()
        print("Modified .cor file COR_DTC at " + str(datetime.datetime.now()))
            
    def set_TEND(tend):
        dotcor = open(corfile, 'r')
        melcor_input = dotcor.readlines()
        dotcor.close()
        # modify the .cor file to use a different end time
        found_tend_line = False
        for line_num in range(1,len(melcor_input)):
            line = melcor_input[line_num]
            if line.strip().startswith("EXEC_TEND") or line.strip().startswith("exec_tend"):
                melcor_input[line_num] = "!" + line
                found_tend_line = True
                prev_TEND.append(float(line.split()[1]))
                print("Original end time was " + str(prev_TEND[0]) + "\n")
            if "END PROGRAM MELCOR" in line:
                melcor_input[line_num] = ""
        if found_tend_line:
            dotcor = open(corfile, 'w') # just overwrite the whole file
            for line in melcor_input:
                dotcor.write(line)
            # record the time dotcor was modified
            #dotcor.write("\n! MelAuto changed tend to " + str(tend) + " at " + str(datetime.datetime.now()) + " after CORDBD error.")
            dotcor.write("\nEXEC_INPUT\n")
            dotcor.write("EXEC_TEND " + "{0:.7f}".format(tend) + "\n")
            dotcor.write("\nEND PROGRAM MELCOR")
            dotcor.close()
            print("Modified .cor file EXEC_TEND at " + str(datetime.datetime.now()))
        else:
            print("Could not find line specifying end time of calculation.")
            sys.exit(1)
            
    # Sets COR_SC coefficient "number", subvalue 1, to "value". If I ever need to do a different subvalue, 
    # another argument will have to be added because the 1 is hard-coded.
    def set_COR_SC(number,value):
        dotcor = open(corfile, 'r')
        melcor_input = dotcor.readlines()
        dotcor.close()
        # modify the .cor file to use a looser tolerance for COR_SC 1502 sensitivity coefficient, in hopes of fixing CORDBD error
        found_cor_sc_line = -1 # increments every time the next card number in the COR_SC block is encountered
        cor_sc_line_num = -1
        cor_sc_total = 0
        endprogline = -1
        alreadyset = False
        for line_num in range(1,len(melcor_input)):
            line = melcor_input[line_num]
            if "END PROGRAM MELCOR" in line:
                melcor_input[line_num] = ""
            if line.strip().startswith("COR_SC") or line.strip().startswith("cor_sc"):
                print("Found cor_sc block.")
                found_cor_sc_line = 0
                cor_sc_line_num = line_num
                cor_sc_total = int(line.split()[1][0]) # The number of cor_sc sensitivity coeffs modified in this block of .cor
            # if we're still in the COR_SC block, and the line starts with the next number in the sequence
            if found_cor_sc_line >= 0 and found_cor_sc_line < cor_sc_total and line.strip().startswith(str(found_cor_sc_line+1)):
                # if it's the line with the 1502(1) sensitivity coefficient
                if line.split()[1] == number and line.split()[3] == "1":
                    if float(line.split()[2]) == value:
                        break
                    else:
                        melcor_input[line_num] = "!" + line
                        melcor_input.insert(line_num+1, str(found_cor_sc_line+1) + " " + number + " " + "{0:.7f}".format(value) + " 1 !" + str(datetime.datetime.now()) + "\n")
                        break
                found_cor_sc_line += 1
                if found_cor_sc_line == cor_sc_total:
                    melcor_input[cor_sc_line_num] = "COR_SC " + str(cor_sc_total + 1) + "\n"
                    melcor_input.insert(line_num+1, str(found_cor_sc_line+1) + " " + number + " " + "{0:.7f}".format(value) + " 1 !" + str(datetime.datetime.now()) + "\n")
                    break
        # if there was no previous COR_SC block
        if found_cor_sc_line < 0: 
            #print("Adding COR_SC block.\n")
            #melcor_input[endprogline] = ""
            melcor_input.append("\nCOR_INPUT")
            melcor_input.append("\nCOR_SC 1" + "\n")
            melcor_input.append("    1 " + number + " " + "{0:.7f}".format(value) + " 1 !" + str(datetime.datetime.now()) + "\n")
            melcor_input.append("END PROGRAM MELCOR")
        dotcor = open(corfile, 'w') # just overwrite the whole file
        for line in melcor_input:
            dotcor.write(line)
        # record the time dotcor was modified
        dotcor.write("\n! MelAuto changed cor_sc " + number + " to " + str(value) + " at " + str(datetime.datetime.now()) + " after CORDBD error.\n")
        dotcor.close()
        print("Modified .cor file COR_SC at " + str(datetime.datetime.now()) + "\n")

    # Sets RN1_CSC coefficient "number", subvalue "subvalue", to "value", at calculation time t_modified. 
    def set_RN1_CSC(number,rnclass,value,subvalue,t_modified):
        dotcor = open(corfile, 'r')
        melcor_input = dotcor.readlines()
        dotcor.close()
        # modify the .cor file to turn off hygroscopic model for cesium, sensitivity coefficient 7170, in hopes of fixing RN1 hygroscopic model error
        found_rn1_csc_line = -1 # increments every time the next card number in the RN1_CSC block is encountered
        rn1_csc_line_num = -1
        rn1_csc_total = 0
        for line_num in range(1,len(melcor_input)):
            line = melcor_input[line_num]
            if "END PROGRAM MELCOR" in line:
                melcor_input[line_num] = ""
            if line.strip().startswith("RN1_CSC") or line.strip().startswith("rn1_csc"):
                print("Found rn1_csc block.")
                found_rn1_csc_line = 0
                rn1_csc_line_num = line_num
                rn1_csc_total = int(line.split()[1][0]) # The number of rn1_csc sensitivity coeffs modified in this block of .cor
            # if we're still in the RN1_CSC block, and the line starts with the next number in the sequence
            if found_rn1_csc_line >= 0 and found_rn1_csc_line < rn1_csc_total and line.strip().startswith(str(found_rn1_csc_line+1)):
                # if it's the line we want to change
                if line.split()[1] == str(number) and line.split()[2] == rnclass and line.split()[4] == str(subvalue):
                    if float(line.split()[3]) == value:
                        break
                    else:
                        melcor_input[line_num] = "!" + line
                        melcor_input.insert(line_num+1, str(found_rn1_csc_line+1) + " " + str(number) + " " + rnclass + " " + "{0:.7f}".format(value)+ " "  + str(subvalue) + " !" + str(datetime.datetime.now()) + ", calculation time " + str(t_modified) + "\n")
                        break
                found_rn1_csc_line += 1
                if found_rn1_csc_line == rn1_csc_total:
                    melcor_input[rn1_csc_line_num] = "RN1_CSC " + str(rn1_csc_total + 1) + "\n"
                    melcor_input.insert(line_num+1, str(found_rn1_csc_line+1) + " " + str(number) + " " + rnclass + " " + "{0:.7f}".format(value)+ " "  + str(subvalue) + " !" + str(datetime.datetime.now()) + ", calculation time " + str(t_modified) + "\n")
                    break
        # if there was no previous RN1_CSC block
        if found_rn1_csc_line < 0: 
            #print("Adding RN1_CSC block.\n")
            #melcor_input[endprogline] = ""
            melcor_input.append("\nRN1_INPUT")
            melcor_input.append("\nRN1_CSC 1" + "\n")
            melcor_input.append("    1 " + + str(number) + " " + rnclass + " " + "{0:.7f}".format(value) + " " + str(subvalue) + " !" + str(datetime.datetime.now()) + ", calculation time " + str(t_modified) + "\n")
            melcor_input.append("END PROGRAM MELCOR")
        dotcor = open(corfile, 'w') # just overwrite the whole file
        for line in melcor_input:
            dotcor.write(line)
        # record the time dotcor was modified
        dotcor.write("\n! MelAuto changed rn1_csc " + str(number) + " " + rnclass + " " + str(subvalue) + " to " + str(value) + " at " + str(datetime.datetime.now()) + ", calculation time " + str(t_modified) + " after RN1 hygroscopic model error.\n")
        dotcor.close()
        print("Modified .cor file RN1_CSC at " + str(datetime.datetime.now())+ ", calculation time " + str(t_modified) + "\n")


    # Set COR_TST line in .cor file
    # values is a string that includes the whole line that should go in .cor
    def set_COR_TST(values):
        dotcor = open(corfile, 'r')
        melcor_input = dotcor.readlines()
        dotcor.close()
        # modify the .cor file to use a new set of COR_TST values
        # for turning off in-vessel oxidation, use "COR_TST  0    0    0    1    0    0    0    0    0    0"
        #found_cor_tst_line = False
        for line_num in range(1,len(melcor_input)):
            line = melcor_input[line_num]
            if "END PROGRAM MELCOR" in line:
                melcor_input[line_num] = ""
            if line.strip().startswith("COR_TST") or line.strip().startswith("cor_tst"):
                melcor_input[line_num] = "!" + line
                #found_cor_tst_line = True
        #print(melcor_input)
        #if found_cor_dtc_line:
        dotcor = open(corfile, 'w') # just overwrite the whole file
        for line in melcor_input:
            dotcor.write(line)
        # record the time dotcor was modified
        #dotcor.write("\n! MelAuto changed cor_dtc to " + str(dtemp) + " " + str(step) + " " + str(iters) + " at " + str(datetime.datetime.now()) + " after CORDBD error.")
        dotcor.write("\nCOR_INPUT\n")
        dotcor.write(values + " ! " + str(datetime.datetime.now()) +  "\n")
        dotcor.write("\nEND PROGRAM MELCOR")
        dotcor.close()
        print("Modified .cor file COR_TST at " + str(datetime.datetime.now()))
    
    
    
    
    # Stuff in main()
    prev_TEND = []
    original_TEND = -1.0e10
    auto_stop_time = [1.0e10] # Time at which to halt execution. Default never.
    
    # Handle CORDBD errors
    cordbd = 0
    prev_cordbd = 0
    tolvt = 0
    prev_tolvt = 0
    hygro = 0
    prev_hygro = 0
    stopval = 0
    prev_auto_stop = False
    disable_ox = False
    prev_t_error = 0
    
    while not stopval:
        #print("\nprev_cordbd = " + str(prev_cordbd) + "\ncordbd = " + str(cordbd))
        # Decide whether to control stdin so the user doesn't have to press 'e'
        auto = (cordbd + prev_cordbd + hygro + prev_hygro > 0)
        if prev_auto_stop:
            auto = True
            prev_auto_stop = False
            print("Resuming after auto-stop.")
        if auto_stop_time[0] < 1.0e10: 
            auto = True
            auto_stop_time[0] = 1.0e10 # So it doesn't just keep doing this over.
        #print("Auto is ", auto)
        stopval = run_melcor(auto, auto_stop_time)
        
        # Check if the stop flag is asking for in-vessel oxidation to be disabled
        try:
            if "COR_TST" in stopval:
                disable_ox = stopval
                stopval = 0
        except:
            pass
            
        if original_TEND < -1.0e9 and len(prev_TEND) > 0:
            original_TEND = prev_TEND[0]
        time.sleep(.1)
        
        #print("Auto-stop time is ", auto_stop_time[0], " stopval ", stopval)
        
        prev_cordbd = cordbd
        prev_tolvt = tolvt
        prev_hygro = hygro
        
        # Check for cordbd or TOLVT or hygroscopic model error
        cordbd = 0
        tolvt = 0
        hygro = 0
        for line in melcor_input:
            if line.strip().startswith('MEL_DIAGFILE') or line.strip().startswith('mel_diagfile'): # tokenize, take the last word in the line, strip the first and last characters (the quotes)
                dia_file = line.strip().split()[-1][:-1][1:]
        # open end of .dia file, print any line containing cordbd
        t_error = None
        try:
            try:
                dia = open(dia_file, 'r')
            except:
                print("Bad filename ", dia)
            try:
                endfile = dia.seek(0,2)
                dia.seek(endfile - 4000)
            except:
                try:
                    endfile = dia.seek(0,2)
                    dia.seek(endfile - 2500)
                except:
                    try:
                        endfile = dia.seek(0,2)
                        dia.seek(endfile - 1000)
                    except:
                        dia.seek(0)
                        print("Diagnostic file is too short. Couldn't check for CORDBD errors.\n")
            try:
                pos = dia.tell()
                diagnostics = dia.readlines()
            except:
                print("Couldn't read diagnostic file.")
            #print(diagnostics)
            try:
                for line in diagnostics:
                    if "ERROR IN SUBROUTINE CORDBD" in line:
                        print(line)
                        cordbd += 1
                        break
                for line in diagnostics:
                    if "TOLVT" in line:
                        print(line)
                        tolvt += 1
                        break
                for line in diagnostics:
                    if "HYGROSCOPIC" in line:
                        print(line)
                        hygro += 1
                        break
            except:
                print("Couldn't iterate over diagnostic file. ", cordbd, tolvt)
            try:
                #print("Cordbd and tolvt are ", cordbd, tolvt)
                if cordbd > 0 or tolvt > 0 or hygro > 0:
                    print("Checking for time.")#, cordbd, tolvt)
                    for line in diagnostics:
                        #print(line)
                        if "<Diagnostic Message>  Time=" in line:
                            # print("Found <Diagnostic Message>  Time=")
                            t_string = line.split()[3]
                            #print("t_string is " + t_string)
                            t_error = float(t_string)
            except:
                print("Last block")
        except:
            print("Error checking diagnostic file for cordbd (etc) error.")
        dia.close()
        
        
        # Do something about cordbd or tolvt error, if there was one.
        if prev_cordbd > 0 and cordbd > 0:
            cordbd = cordbd + prev_cordbd
        if auto_stop_time[0] < 1.0e10:
            cordbd = prev_cordbd # We're going back to the last restart, so gotta do whatever we did before.
            #print("Setting cordbd to ", cordbd, " again for auto-stop")
        if cordbd > 0:
            dotcor = open(corfile, 'a') # append
            if t_error == None:
                print("Error getting time of error from diagnostic file.")
                sys.exit(1)
            if cordbd == 1:
                print("Level 1 CORDBD error.\n")
                startcycle = -1
                starttime = -1.e6
                set_COR_DTC(100,0.00001,256)
                set_TEND(t_error+3.0)
                dotcor.write("\n! Level 1 CORDBD error at " + str(t_error) + ".\n")
            if cordbd == 2:
                print("Level 2 CORDBD error.\n")
                startcycle = -1
                starttime = -1.e6
                set_COR_DTC(200,0.00001,300)
                set_TEND(t_error+5.0)
                dotcor.write("\n! Level 2 CORDBD error at " + str(t_error) + ".\n")
            if cordbd == 3:
                print("Level 3 CORDBD error.\n")
                startcycle = -1
                starttime = -1.e6
                set_COR_DTC(300,0.00001,400)
                set_TEND(t_error+4.0)
                set_COR_SC("1502",1.0e-4)
                dotcor.write("\n! Level 3 CORDBD error at " + str(t_error) + ".\n")
            if cordbd == 4:
                print("Level 4 CORDBD error.\n")
                dotcor.write("\n! Level 4 CORDBD error at " + str(t_error) + ".\n")
                # Find an earlier restart to go back to.
                restarts = get_restarts()
                for i in range(-1,-len(restarts),-1):
                    if restarts[i][0] < t_error - 5:
                        #startcycle = restarts[i][1]
                        startcycle = -2
                        starttime = restarts[i][0] - 1.0
                        break
                print("Going back to " + str(starttime) + ".\n")
                set_COR_DTC(30,0.0001,256)
                set_TEND(t_error - 4)
                set_COR_SC("1502",1.0e-6)
                if not stopval:
                    stopval = run_melcor(True, auto_stop_time)
                    
                    # Check if the stop flag is asking for in-vessel oxidation to be disabled
                    try:
                        if "COR_TST" in stopval:
                            disable_ox = stopval
                            stopval = 0
                    except:
                        pass
                startcycle = -1
                starttime = -1.e6
                set_COR_DTC(300,0.00001,400)
                set_TEND(t_error + 4)
                set_COR_SC("1502",1.0e-3)
            if cordbd > 4:
                dotcor.write("\n! Level 5 CORDBD error at " + str(t_error) + ". Giving up.\n")
                print("\nResistant CORDBD error. Exiting after 4 tries.\n")
                sys.exit(1)
            dotcor.close()
        elif prev_cordbd > 0:   # change COR_DTC and COR_SC back to default values
            set_COR_DTC(30,0.001,64)
            set_TEND(prev_TEND[0])
            #print("Setting cor_sc.\n")
            #time.sleep(45)
            set_COR_SC("1502",1.0e-6)
        elif tolvt > 0:
            set_TEND(t_error+5.0)
            set_COR_SC("1504",1.0e-2)
        elif prev_tolvt > 0:
            set_COR_SC("1504",1.0e-4)
            set_TEND(prev_TEND[0])
        elif hygro > 0: # There has been an "RN1 hygroscopic model" error,
            # so disable the hygroscopic model for cesium by setting everything to 0.
            if t_error == None:
                print("Error getting time of error from diagnostic file.")
                sys.exit(1)
            else:
                prev_t_error = t_error # save this to use later
            set_TEND(t_error+10.0)
            startcycle = -1
            starttime = -1.e6
            set_RN1_CSC("7170","CS",0.0,"3",t_error)
            set_RN1_CSC("7170","CSI",0.0,"3",t_error)
            set_RN1_CSC("7170","CSM",0.0,"3",t_error)
            set_RN1_CSC("7170","CS",0.0,"4",t_error)
            set_RN1_CSC("7170","CSI",0.0,"4",t_error)
            set_RN1_CSC("7170","CSM",0.0,"4",t_error)
        elif prev_hygro > 0: # Change hygroscopic model back to default values
            set_RN1_CSC("7170","CS",3.95,"3",prev_t_error+10.0)
            set_RN1_CSC("7170","CSI",0.44,"3",prev_t_error+10.0)
            set_RN1_CSC("7170","CSM",0.67,"3",prev_t_error+10.0)
            set_RN1_CSC("7170","CS",3.95,"4",prev_t_error+10.0)
            set_RN1_CSC("7170","CSI",2.25,"4",prev_t_error+10.0)
            set_RN1_CSC("7170","CSM",0.67,"4",prev_t_error+10.0)
            set_TEND(prev_TEND[0])
        elif auto_stop_time[0] < 1.0e10:
            print("Setting end time to auto-stop time.")
            set_TEND(auto_stop_time[0])
            if original_TEND < -1.0e9:
                original_TEND = prev_TEND[0]
            prev_TEND[0] = auto_stop_time[0]
            restarts = get_restarts()
            for i in range(-1,-len(restarts),-1):
                if restarts[i][0] < auto_stop_time[0]:
                    #startcycle = restarts[i][1]
                    startcycle = -2
                    starttime = restarts[i][0] - 1.0
                    break
            print("Going back to " + str(starttime) + ".\n")
        elif len(prev_TEND) > 0 and original_TEND > prev_TEND[0]: # if resuming from an auto-stop
            print("Setting end time to its original value, ", original_TEND, "\n")
            prev_TEND[0] = original_TEND
            original_TEND = -1.0e10
            startcycle = -1
            starttime = -1.e6
            set_TEND(prev_TEND[0])
            prev_auto_stop = True
            if disable_ox != False:
                set_COR_TST(disable_ox)
                disable_ox = False
        else:
            break
    # End while not stopval
    # no more cordbd errors to fix
    print("Finished calculation at " + str(datetime.datetime.now()))

if __name__ == '__main__':
    main_function()

# compile with command:
# python c:\python34\scripts\cxfreeze ./melauto.py

# things to do:
# x use any version of melcor that's in the same folder (print which one it is)
# x record start and stop times, and run time
# x take .cor file as command line arg
# x take cycle number as command line argument
# x process ctrl-c correctly
# x take "restarts" as command line argument and print out restart times
# x open and modify .cor file
# --x---pass through user interruptions to melcor (read stdin?) with keyboard interrupt exception
# x process melcor output to determine if there's a cordbd
# x read stdout
# x watch for TOLVT errors

# x watch for the timestep to stay too low for too long
# do something about the timestep staying too low for too long
#   go back, increase CVH_SC 4415 and 4412 to 1.0e-7 and 0.01 (or higher temporarily)
#   go back to the last dt(MAX) and increase the max dt?

# watch for CVNTQE errors (and do what, exactly?)
# CORLHD (CORRN1) error: go back and tighten cor_sc params
# read the ptf. use readptf?

# Make messages written in .cor file specify the calc time and cycle as well as the real time. Including commenting things out.
# Also make it list all the changes at the end, including commenting things out.
