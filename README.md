# MelAuto

MelAuto
Erick Ball
Updated 22 March 2016, 29 July 2016, 3 Feb 2017 (bugfix), 30 Oct 2017

This program is a Python wrapper for the MELCOR executable, intended to simplify the handling of long MELCOR runs by reducing
the number of human interventions necessary.
Place the executable (and the python34.dll library) into the same folder as the MELCOR executable, and run it instead of MELCOR.
It makes a copy of the specified .cor file so that it is not necessary to modify the original.

Features:
    MelAuto will automatically handle most instances of "ERROR IN SUBROUTINE CORDBD" by changing COR sensitivity coefficients. In 
        tough cases it will go back to an earlier restart to improve its chances. It should also handle basic errors of the 
        "Increase TOLVT" variety, though this has not been tested.
    It permits easy reading of restarts from the .mes file, and filters out the ones that have been overwritten.
    It allows you to specify a restart cycle at the command line.
    It keeps track of when MELCOR starts and stops running, and of any changes it makes to the .cor.
    It warns you if you are about to overwrite some of your restarts by starting from an earlier cycle.
    It watches MELCOR output for the flag "stopcalc" to be included in a control function message (or any other output). If seen, it 
        will note the simulation time, terminate the calculation, and begin it from the last restart with the noted time as the new end 
        time so that a restart is written at that point. It then resumes normal running (but could also make changes to .cor, like 
        COR_TST mods). The flag it watches for can be easily changed in the code and recompiled so it's not necessary to change the deck.
        Note that there is about 0.1 second of wiggle room in the stop time to ensure that it does not get stuck in a loop. This is 
        necessary because the CF_MSG function only displays the calculation time to a tenth of a second precision.
    Update: if the line that has "stopcalc" also contains "disable oxidation" then when it gets back to that point and resumes normal 
        running it will also modify COR_TST to stop in-vessel oxidation.
    
Bugs:
    Sending the stopcalc flag may cause loss of a significant amount of calculation time because MelAuto cannot force MELCOR to save the 
        current state.
    When no .rst file is present MelAuto should give an appropriate error message.

Command line arguments:
    Required:
        corfile          The name of a .cor file
    Optional:
        restarts  or r   Tells it to read all "Restart written" lines from the .mes file (if present) and print them to the screen.
        NCYCLE           The cycle number at which to restart the calculation. This allows you to avoid changing the NCYCLE parameter 
            directly in .cor, which can lead to accidental erasing of data.
            Enter cycle number 2 to get a slower, but maybe more accurate, list of the restarts available in the .rst file.
        
        Example: melauto.exe SBO.cor 179511
        (starts from cycle 179511)
        
Change log:
    Version 9 (2017-10-30): Added an output file that tells the user (in the filename) how many times it has restarted MELCOR.
    Version 8 (2017-10-27): Added ability to handle hygroscopic model errors.
    Version 7: Added the ability to choose a restart using the time, instead of the cycle number.
    Version 6 (2016-07-29): Added copying of old restart file so it doesn't get written over by accident.
    Version 5 (2016-03-28): fixed bug that causes an error when "DT(HS )= " appears in the MELCOR output and changes the numbers of the tokens.
    Also added some wiggle room to the auto-stop timing to allow the message to appear slightly earlier or later on the second 
    try. Not sure why this is necessary, it should be an identical calculation.
