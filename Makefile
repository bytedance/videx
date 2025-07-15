# contrib/videx/Makefile

MODULE_big = videx
OBJS = \
	$(WIN32RES) \
	src/pg/stats.o \
	src/pg/videxam.o \

EXTENSION = videx
DATA = videx--1.0.sql
PGFILEDESC = "videx - virtual index extension for PostgreSQL"

REGRESS_OPTS = --temp-config $(top_srcdir)/contrib/videx/videx.conf
REGRESS = videx 

TAP_TESTS = 1

ifdef USE_PGXS
PG_CONFIG = pg_config
PGXS := $(shell $(PG_CONFIG) --pgxs)
include $(PGXS)
else
subdir = contrib/videx 
top_builddir = ../..
include $(top_builddir)/src/Makefile.global
include $(top_srcdir)/contrib/contrib-global.mk
endif
