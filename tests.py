# -*- coding: utf-8 -*-
"""

unit tests for liikelaajuus
automatically run by 'nose2'

@author: jussi (jnu@iki.fi)
"""

from nose.tools import assert_set_equal, assert_in, assert_equal
from xlrd import open_workbook
import io
import json
from reporter import Report
import text_templates
from PyQt5 import uic, QtGui, QtWidgets
import liikelaajuus
import sys
import hashlib  # spark another owl...


fn_xls_template = "rom_excel_template.xls"
uifile = "tabbed_design.ui"

""" reference json data. must be updated if variables are changed. """
fn_emptyvals = "testdata/empty.json"
fn_ref = "testdata/anonyymi.json"

""" reference reports. must be updated if some aspect of reporting
changes. use regen_ref_data() below. """
fn_txt_ref = "testdata/anonyymi.txt"
fn_xls_ref = "testdata/anonyymi.xls"

""" written out by tests below """
fn_xls_out = "testdata/nosetests_xls_report.xls"
fn_out = "testdata/nosetests.json"

with io.open(fn_emptyvals, 'r', encoding='utf-8') as f:
    data_emptyvals = json.load(f)

app = QtWidgets.QApplication(sys.argv)  # needed for Qt stuff to function

""" Create instance of app that is not shown on screen (also event loop is not
entered) but can be used to test various methods. NOTE: any existing temp file
may be deleted by the unit tests """
eapp = liikelaajuus.EntryApp(check_temp_file=False)


""" aux functions """


def file_md5(fn):
    """ Get MD5 sum of file in a dumb way. Works for small files. """
    return hashlib.md5(open(fn, 'rb').read()).hexdigest()


def regen_ref_data():
    """ Create new reference reports from reference data. Overwrites previous
    ref reports without asking. Only run when reporting is known to be correct.
    """
    app = QtWidgets.QApplication(sys.argv)  # needed for Qt stuff to function
    eapp = liikelaajuus.EntryApp(check_temp_file=False)
    eapp.load_file(fn_ref)
    report = Report(eapp.data_with_units, eapp.vars_default)
    report.make_excel(fn_xls_ref, fn_xls_template)
    report_txt = report.make_report()
    with io.open(fn_txt_ref, 'w', encoding='utf-8') as f:
        f.write(report_txt)


""" BEGIN TESTS """


def test_save():
    """ Test saving data """
    eapp.load_file(fn_ref)
    eapp.save_file(fn_out)
    assert_equal(file_md5(fn_ref), file_md5(fn_out))


def test_text_report():
    """ Use app to load reference data and generate text report, compare
    with ref report """
    eapp.load_file(fn_ref)
    report = Report(eapp.data, eapp.vars_default(), eapp.units())
    report_txt = report.make_text_report()
    with io.open(fn_txt_ref, 'r', encoding='utf-8') as f:
        report_ref = f.read()
    assert_equal(report_ref, report_txt)


def test_xls_report():
    """ Use app to load reference data and generate xls report, compare
    with ref report """
    eapp.load_file(fn_ref)
    report = Report(eapp.data, eapp.vars_default(), eapp.units())
    report.make_excel(fn_xls_out, fn_xls_template)
    assert_equal(file_md5(fn_xls_out), file_md5(fn_xls_ref))


def test_xls_template():
    """ Test validity of xls report template: no unknown vars
    in template """
    rb = open_workbook(fn_xls_template, formatting_info=True)
    r_sheet = rb.sheet_by_index(0)
    for row in range(r_sheet.nrows):
        for col in range(r_sheet.ncols):
            cl = r_sheet.cell(row, col)
            varname = cl.value
            if varname:
                # extract all fields (variable names)
                flds = Report.get_field(varname)
                for fld in flds:
                    assert_in(fld, data_emptyvals)


def test_text_template():
    """ Test validity of text template: all vars in report and
    no unknown vars in report """
    vars = set()
    for li in text_templates.report:
        vars.update(set(Report.get_field(li)))
    assert_set_equal(vars, set(data_emptyvals.keys()))


def test_widgets():
    """ Check classes of Qt widgets. Check that variable names derived
    form the widgets match the empty json file. """
    # cannot refer to Qt widgets without creating a QApplication
    mainui = uic.loadUi(uifile)
    widgets = mainui.findChildren(QtWidgets.QWidget)
    varnames = set()
    for w in widgets:
        wname = w.objectName()
        varname = ''
        if wname[:2] == 'sp':
            assert(w.__class__ == QtWidgets.QSpinBox or
                   w.__class__ == QtWidgets.QDoubleSpinBox)
            varname = wname[2:]
        elif wname[:2] == 'ln':
            assert(w.__class__ == QtWidgets.QLineEdit)
            varname = wname[2:]
        elif wname[:2] == 'cb':
            assert(w.__class__ == QtWidgets.QComboBox)
            varname = wname[2:]
        elif wname[:3] == 'cmt':
            assert(w.__class__ == QtWidgets.QTextEdit)
            varname = wname
        elif wname[:2] == 'xb':
            assert(w.__class__ == QtWidgets.QCheckBox)
            varname = wname[2:]
        elif wname[:3] == 'csb':
            assert(w.__class__ == liikelaajuus.CheckDegSpinBox)
            varname = wname[3:]
        if varname:
            varnames.add(unicode(varname))
    assert_set_equal(varnames, set(data_emptyvals.keys()))
