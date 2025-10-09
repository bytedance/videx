CREATE FUNCTION videx_analyze(source regclass, target regclass)
RETURNS void
AS 'videx', 'videx_analyze'
LANGUAGE C STRICT;

CREATE OR REPLACE FUNCTION videx_tableam_handler(internal)
RETURNS table_am_handler AS 'videx', 'videx_tableam_handler'
LANGUAGE C STRICT;

CREATE ACCESS METHOD videx TYPE TABLE HANDLER videx_tableam_handler;
