# -*- coding: utf-8 -*-
"""
Configuration for liikelaajuus
"""

from pathlib import Path
import sys
from datetime import date


# XXX: these should eventually go into a proper config file
class Config(object):
    """ The 'not measured' value for spinboxes. For regular spinboxes, this
    is the value that gets written to data files, but it does not affect
    the value shown next to the spinbox (which is set in Qt Designer).
    For the CheckDegSpinBox class, this is also the value shown next to the
    widget in the user interface. """
    spinbox_novalue_text = 'Ei mitattu'
    # 'yes' and 'no' values for checkboxes. Written to data files.
    checkbox_yestext = 'Kyllä'
    # the (hacky) idea here is that by virtue of case sensitivity, 'EI' can be
    # changed in the reports by search&replace without affecting other 'Ei'
    checkbox_notext = 'EI'
    # Set dirs according to platform
    if sys.platform == 'win32':
        tmp_path = Path('/Temp')
        # default path for saved JSON data; only used by file dialogs
        data_root_path = Path('Z:/Other Data_May2013/ROM/ROM_%d' % date.today().year)
    else:  # hopefully POSIX
        tmp_path = Path('/tmp')
        data_root_path = Path('/')
    text_report_path = data_root_path / 'Raportit'
    excel_report_path = data_root_path / 'Raportit_Excel'
    tmpfile_path = tmp_path / 'liikelaajuus_tmp.json'
    json_backup_path = Path('Z:/Misc/ROM_backup')
    # prefix of default Excel report filename
    excel_report_prefix = 'Excel_'
    # prefix of default text report filename
    text_report_prefix = 'Raportti_'
    # prefix of isokinetic text report filename
    isokin_text_report_prefix = 'Isokin_Raportti_'
    # exceptions that might be generated when parsing and loading/saving json
    # these should all be caught
    json_io_exceptions = (UnicodeDecodeError, EOFError, IOError, TypeError)
    json_filter = 'JSON files (*.json)'
    text_filter = 'Text files (*.txt)'
    excel_filter = 'Excel files (*.xls)'
    global_fontsize = 11
    traceback_file = 'traceback.txt'
    help_url = 'https://github.com/jjnurminen/liikelaaj/wiki'
    # template paths
    xls_template = 'templates/rom_excel_template.xls'
    text_template = 'templates/text_template.py'
    isokin_text_template = 'templates/isokin_text_template.py'
    # allowing multiple instances is problematic since they share the same
    # backup file (tmpfile)
    allow_multiple_instances = False
