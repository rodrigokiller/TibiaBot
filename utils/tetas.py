import asyncio

import io

from PIL import Image
from PIL import ImageDraw
from discord import Colour
import datetime
import urllib
import urllib.request
import aiohttp
import re
from datetime import datetime, date, timedelta
from calendar import timegm
import time

from utils.database import userDatabase, tibiaDatabase
from config import highscores_categories, network_retry_delay
from utils.messages import EMOJI
from .general import log, global_online_list, get_local_timezone

# Constants
ERROR_NETWORK = 0
ERROR_DOESNTEXIST = 1
ERROR_NOTINDATABASE = 2

# Tibia.com URLs:
url_character = "https://secure.tibia.com/community/?subtopic=characters&name="
url_guild = "https://secure.tibia.com/community/?subtopic=guilds&page=view&GuildName="
url_guild_online = "https://secure.tibia.com/community/?subtopic=guilds&page=view&onlyshowonline=1&"
url_house = "https://secure.tibia.com/community/?subtopic=houses&page=view&houseid={id}&world={world}"
url_highscores = "https://secure.tibia.com/community/?subtopic=highscores&world={0}&list={1}&profession={2}&currentpage={3}"

KNIGHT = ["knight", "elite knight", "ek", "k", "kina", "eliteknight","elite"]
PALADIN = ["paladin", "royal paladin", "rp", "p", "pally", "royalpaladin", "royalpally"]
DRUID = ["druid", "elder druid", "ed", "d", "elderdruid", "elder"]
SORCERER = ["sorcerer", "master sorcerer", "ms", "s", "sorc", "mastersorcerer", "master"]
MAGE = DRUID + SORCERER + ["mage"]
NO_VOCATION = ["no vocation", "no voc", "novoc", "nv", "n v", "none", "no", "n", "noob", "noobie", "rook", "rookie"]


highscore_format = {"achievements": "{0} __achievement points__ are **{1}**, on rank **{2}**",
                    "axe": "{0} __axe fighting__ level is **{1}**, on rank **{2}**",
                    "club": "{0} __club fighting__ level is **{1}**, on rank **{2}**",
                    "distance": "{0} __distance fighting__ level is **{1}**, on rank **{2}**",
                    "fishing": "{0} __fishing__ level is **{1}**, on rank **{2}**",
                    "fist": "{0} __fist fighting__ level is **{1}**, on rank **{2}**",
                    "loyalty": "{0} __loyalty points__ are **{1}**, on rank **{2}**",
                    "magic": "{0} __magic level__ is **{1}**, on rank **{2}**",
                    "magic_ek": "{0} __magic level__ is **{1}**, on rank **{2}** (knights)",
                    "magic_rp": "{0} __magic level__ is **{1}**, on rank **{2}** (paladins)",
                    "shielding": "{0} __shielding__ level is **{1}**, on rank **{2}**",
                    "sword": "{0} __sword fighting__ level is **{1}**, on rank **{2}**"}

tibia_worlds = ["Amera", "Antica", "Astera", "Aurera", "Aurora", "Bellona", "Belobra", "Beneva", "Calmera", "Calva",
                "Calvera", "Candia", "Celesta", "Chrona", "Danera", "Dolera", "Efidia", "Eldera", "Ferobra", "Fidera",
                "Fortera", "Garnera", "Guardia", "Harmonia", "Honera", "Hydera", "Inferna", "Iona", "Irmada", "Julera",
                "Justera", "Kenora", "Kronera", "Laudera", "Luminera", "Magera", "Menera", "Morta", "Mortera",
                "Neptera", "Nerana", "Nika", "Olympa", "Osera", "Pacera", "Premia", "Pythera", "Guilia", "Refugia",
                "Rowana", "Secura", "Serdebra", "Shivera", "Silvera", "Solera", "Tavara", "Thera", "Umera", "Unitera",
                "Veludera", "Verlana", "Xantera", "Xylana", "Yanara", "Zanera", "Zeluna"]