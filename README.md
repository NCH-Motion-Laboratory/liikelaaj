PyQt app for input of movement range data (in Finnish).

Ohjelma liikelaajuusmittausten syöttämiseen, tallentamiseen ja raportointiin.

NOTE: this was originally a standalone application that saved data in JSON
format (see liikelaajuus.py). Currently, a slightly modified version
(sql_entryapp.py) is used by the gait database (gaitbase) as a data entry
interface. Instead of writing JSON, it gets a handle to the database and saves the
data there. The standalone version is deprecated and no longer maintained.
