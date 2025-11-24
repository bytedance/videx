#!/bin/bash

RESET="\033[0m"
BOLD="\033[1m"
RED="\033[31m"
GREEN="\033[32m"
YELLOW="\033[33m"
BLUE="\033[34m"

echo -e "${BLUE}==========================================${RESET}"
echo -e "${GREEN}${BOLD}PostgreSQL Version:${RESET} $(pg_config --version)"
echo -e "${BLUE}==========================================${RESET}"


echo -e "${YELLOW}${BOLD}Cleaning previous builds...${RESET}"
make clean
echo -e "${YELLOW}Clean complete.${RESET}"


echo -e "${YELLOW}${BOLD}Building the extension...${RESET}"
make -j64 PG_CONFIG=/home/yyk/videx-for-pg/bin/pg_config
echo -e "${YELLOW}Build complete.${RESET}"


echo -e "${YELLOW}${BOLD}Installing the extension...${RESET}"
sudo make install PG_CONFIG=/home/yyk/videx-for-pg/bin/pg_config
echo -e "${GREEN}Installation complete.${RESET}"


echo -e "${BLUE}==========================================${RESET}"
echo -e "${GREEN}${BOLD}Setup finished successfully!${RESET}"
echo -e "${BLUE}==========================================${RESET}"
