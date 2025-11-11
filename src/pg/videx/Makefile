# contrib/videx/Makefile

MODULE_big = videx
OBJS = \
	$(WIN32RES) \
	pg/videx/stats.o \
	pg/videx/videxam.o \
	pg/videx/videx_json_item.o \

CURRENT_DIR := $(shell pwd)
$(info CURRENT_DIR = $(CURRENT_DIR))

SHLIB_LINK_INTERNAL = $(libpq) -lstdc++ -lcurl -L/usr/local/lib -luv -lstdc++ -L/usr/lib/x86_64-linux-gnu
CFLAGS += -std=c11  -I/usr/local/include 
PG_CPPFLAGS =  -fPIC -I$(libpq_srcdir) -I$(CURRENT_DIR)/pg/videx 

EXTENSION = videx
DATA = videx--1.0.sql
PGFILEDESC = "videx - virtual index extension for PostgreSQL"

REGRESS_OPTS = --temp-config $(top_srcdir)/contrib/videx/videx.conf
REGRESS = videx 

CXX = g++
CC = gcc

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
