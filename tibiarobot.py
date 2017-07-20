# -*- coding: utf-8 -*-

import telepot
import telepot.aio
import os
import sys
import random
import requests
import asyncio
import io
import time
import json

from telepot.aio.delegate import per_chat_id, create_open, pave_event_space
from telepot.aio.routing import by_command
from urllib.request import urlopen
from datetime import datetime, date
from pytz import timezone

from config import *
from utils.database import tracked_worlds
from utils.general import is_numeric, get_time_diff, join_list, get_brasilia_time_zone
from utils.loot import loot_scan
from utils.messages import EMOJI, split_message
from utils.tibia import *

command_list = ['start','stats','whois','share','guild','item','monster','blessing','blessings','spell','spells']

class Tibia(telepot.aio.helper.ChatHandler):  
  def __init__(self, *args, **kwargs):
    super(Tibia, self).__init__(*args, **kwargs)    
      
  @asyncio.coroutine
  def on_chat_message(self, msg):
    content_type, chat_type, chat_id = telepot.glance(msg)
    print(content_type, chat_type, chat_id)
    
    if content_type != 'text':
      yield from self.sender.sendMessage("Eu não entendo...")
      return
      
    command = msg['text'].strip().lower()
    param = None
    #split = by_command(command, '/', ' ')
    split = command.split(" ", 1)
    if split[0][:1] == "/" and split[0].lower()[1:] in command_list:
        if len(split) > 1:
            command = split[0].lower()
            param = split[1]
        else:
            command = command.lower()  
    else:
      yield from self.sender.sendMessage('Comando não reconhecido')
      return
    
    #whois 
    if command == '/whois':
      if param is None:
        yield from self.sender.sendMessage('Diga-me o nome de um personagem. Exemplo:\n' \
                                           '`/whois Sor Killer`', parse_mode='Markdown') 
        return
        
      char = yield from get_character(param)
      if char == ERROR_DOESNTEXIST:
        yield from self.sender.sendMessage("Não encontrei um personagem com este nome")
      elif char == ERROR_NETWORK:
        yield from self.sender.sendMessage("Desculpe, não consegui encontrar informações deste personagem. Tente novamente mais tarde...")
      else:  
        embed = self.get_char_string(char)
        yield from self.sender.sendMessage(embed, parse_mode='Markdown') 
        
    #share      
    if command == '/share':
      """Shows the sharing range for that level or character

      There's two ways to use this command:
      /share level
      /share char_name"""
      if param is None:
          yield from self.sender.sendMessage("Você precisa me dar um nível ou um nome de personagem. Exemplos:\n" \
                                             "`/share 100\n" \
                                             "/share Sor Killer`", parse_mode='Markdown')
          return
      name = ""
      # Check if param is numeric
      try:
          level = int(param)
      # If it's not numeric, then it must be a char's name
      except ValueError:
          char = yield from get_character(param)
          if type(char) is dict:
              level = int(char['level'])
              name = char['name']
          else:
              yield from self.sender.sendMessage('Não há personagem com este nome.')
              return
      if level <= 0:
          replies = ["Nível inválido.",
                     "Acredito que este não é um nível válido.",
                     "Você está fazendo isso errado!",
                     "Não, você não pode dividir experiência com ninguém, sério.",
                     "Você provavelmente precisa de mais alguns níveis.",
                     "I'm sorry Dave, I'm afraid i can't do that"
                     ]
          yield from self.sender.sendMessage(random.choice(replies))
          return
      low, high = get_share_range(level)
      if name == "":
          reply = "Um nível {0} pode dividir experiência com pessoas do nível *{1}* até *{2}*.".format(level, low, high)
      else:
          reply = "*{0}* ({1}) pode dividir experiência com pessoas do nível *{2}* até *{3}*.".format(name, level, low, high)
      yield from self.sender.sendMessage(reply, parse_mode='Markdown')         

    #guild      
    if command == '/guild':
      """Checks who is online in a guild"""
      if param is None:
          yield from self.sender.sendMessage("Preciso do nome da guild. Exemplo:\n" \
                                             "`/guild guild_name`", parse_mode='Markdown')
          return

      guild = yield from get_guild_online(param)
      if guild == ERROR_DOESNTEXIST:
          yield from self.sender.sendMessage("A guild {0} não existe.".format(name))
          return
      if guild == ERROR_NETWORK:
          yield from self.sender.sendMessage("Você poderia repetir o comando? Eu tive um problema ao me comunicar com o servidor.")
          return

      embed = ''
      if guild.get("guildhall") is not None:
          guildhouse = yield from get_house(guild["guildhall"])
          if type(guildhouse) is dict:
              embed += "They own the guildhall [{0}]({1}).\n".format(guild["guildhall"],
                                                                                url_house.format(id=guildhouse["id"],
                                                                                                 world=guild["world"])
                                                                                )
          else:
              # In case there's no match in the houses table, we just show the name.
              embed += "They own the guildhall **{0}**.\n".format(guild["guildhall"])

      if len(guild['members']) < 1:
          embed += "Ninguém está conectado."
          yield from self.sender.sendMessage(embed, parse_mode='Markdown')
          return

      plural = ""
      plural2 = ""
      if len(guild['members']) > 1:
          plural = "es"
          plural2 = "s"
      embed += "Tem {0} jogador{1} conectado{2}:".format(len(guild['members']), plural, plural2)
      current_field = ""
      result = ""
      for member in guild['members']:
          if current_field == "":
              current_field = member['rank']
          elif member['rank'] != current_field and member["rank"] != "":
              embed += 'name: ' + current_field + ' value: ' + result
              #embed.add_field(name=current_field, value=result, inline=False)
              result = ""
              current_field = member['rank']

          member["title"] = ' (*' + member['title'] + '*)' if member['title'] != '' else ''
          member["vocation"] = get_voc_abb(member["vocation"])

          result += "{name} {title} -- {level} {vocation}\n".format(**member)
      #embed.add_field(name=current_field, value=result, inline=False)
      embed += 'name: ' + current_field + ' value: ' + result
      yield from self.sender.sendMessage(embed, parse_mode='Markdown')    

    #item      
    if command == '/item':
      """Checks an item's information
      Shows name, picture, npcs that buy and sell and creature drops"""      
      if param is None:
          yield from self.sender.sendMessage("Diga-me o nome do item que você quer pesquisar. Exemplo:\n" \
                                             "`/item golden legs`", parse_mode='Markdown')
          return
      item = get_item(param)
      if item is None:
          yield from self.sender.sendMessage("Eu não pude encontrar um item com este nome.")
          return

      #embed = ''
      if type(item) is list:
          embed = "\n".join(item)
          embed = "Eu não pude encontrar um item com este nome. Talvez você quis dizer algum destes?\n" + embed
          yield from self.sender.sendMessage(embed)
          return

      # Attach item's image only if the bot has permissions
      filename = item['name'] + ".png"
      while os.path.isfile(filename):
          filename = "_" + filename
      with open(filename, "w+b") as f:
          f.write(bytearray(item['image']))
          f.close()

      with open(filename, "r+b") as f:
          yield from self.sender.sendPhoto(f)
          f.close()
      os.remove(filename)
      
      #embed = item      
      yield from self.sender.sendMessage('Ainda não está pronta a funcionalidade de listar o drop, monstro e outras informações sobre o item')      
    
    #monster      
    if command == '/monster':
      """Gives information about a monster"""      
      if param is None:
          yield from self.sender.sendMessage("Diga-me o nome do monstro que você quer persquisar. Exemplos:\n" \
                                             "`/monster demon\n" \
                                             "/monster tibia robot`", parse_mode='Markdown')
          return

      if param.lower() == 'tibia robot':
          yield from self.sender.sendMessage(random.choice(["*Tibia Robot* é muito forte para você poder caçá-lo!",
                                                 "Claro, claro, você mata *uma* criancinha e aí do nada você é um monstro!",
                                                 "EU NÃO SOU UM MONSTRO",
                                                 "Eu sou um monstro, então? Vou lembrar disso, humano...🔥",
                                                 "Você quis dizer *futuro imperador do mundo*.",
                                                 "Você não é uma boa pessoa. Você sabe disso, certo?",
                                                 "Acho que nós dois sabemos que isso não irá acontecer.",
                                                 "Você não pode me caçar.",
                                                 "Seria engraçado... se eu fosse programado para rir."]), parse_mode='Markdown')
          return
      monster = get_monster(param)
      if monster is None:
          yield from self.sender.sendMessage("Eu não pude encontrar um monstro com este nome.")
          return

      if type(monster) is list:
          embed = "\n".join(monster)
          embed = "Eu não pude encontrar um monstro com este nome. Talvez você quis dizer algum destes?\n" + embed          
          yield from self.sender.sendMessage(embed)
          return

      # Attach item's image only if the bot has permissions
      filename = monster['name'] + ".png"
      while os.path.isfile(filename):
          filename = "_" + filename
      with open(filename, "w+b") as f:
          f.write(bytearray(monster['image']))
          f.close()
      # Send monster's image
      with open(filename, "r+b") as f:
          yield from self.sender.sendPhoto(f)
          f.close()
      os.remove(filename)

      #long = ctx.message.channel.is_private or ctx.message.channel.name == ask_channel_name
      #embed = self.get_monster_embed(ctx, monster, long)

      yield from self.sender.sendMessage('Ainda não está pronta a funcionalidade de listar informações do monstro')     
    
    #stats      
    if command == '/stats':
      """Calculates character stats

      There are 3 ways to use this command:
      /stats player
      /stats level,vocation
      /stats vocation,level"""
      invalid_arguments = "Parâmetros inválidos. Exemplos:\n" \
                          "`/stats player\n" \
                          "/stats level,vocation\n" \
                          "/stats vocation,level`"
      if param is None:
          yield from self.sender.sendMessage(invalid_arguments, parse_mode='Markdown')
          return
      params = param.split(",")
      char = None
      if len(params) == 1:
          _digits = re.compile('\d')
          if _digits.search(params[0]) is not None:
              yield from self.sender.sendMessage(invalid_arguments, parse_mode='Markdown')
              return
          else:
              char = yield from get_character(params[0])
              if char == ERROR_NETWORK:
                  yield from self.sender.sendMessage("Desculpe, pode tentar novamente?")
                  return
              if char == ERROR_DOESNTEXIST:
                  yield from self.sender.sendMessage("O personagem *{0}* não existe!".format(params[0]), parse_mode='Markdown')
                  return
              level = int(char['level'])
              vocation = char['vocation']
      elif len(params) == 2:
          try:
              level = int(params[0])
              vocation = params[1]
          except ValueError:
              try:
                  level = int(params[1])
                  vocation = params[0]
              except ValueError:
                  yield from self.sender.sendMessage(invalid_arguments, parse_mode='Markdown')
                  return
      else:
          yield from self.sender.sendMessage(invalid_arguments, parse_mode='Markdown')
          return
      stats = get_stats(level, vocation)
      if stats == "low level":
          yield from self.sender.sendMessage("Nem mesmo *você* pode ser tão baixo assim!", parse_mode='Markdown')
      elif stats == "high level":
          yield from self.sender.sendMessage("Porque você quer saber isso? Você _nunca_ chegará neste nível "+str(chr(0x1f644)), parse_mode='Markdown')
      elif stats == "bad vocation":
          yield from self.sender.sendMessage("Eu não conheço essa vocação...")
      elif stats == "bad level":
          yield from self.sender.sendMessage("O nível precisa ser um número!")
      elif isinstance(stats, dict):
          if stats["vocation"] == "no vocation":
              stats["vocation"] = "with no vocation"
          if char:
              pronoun = "ele" if char['gender'] == "male" else "ela"
              yield from self.sender.sendMessage("*{5}* é um {1} de nível *{0}*, {6} tem:"
                                      "\n\t*{2:,}* HP"
                                      "\n\t*{3:,}* MP"
                                      "\n\t*{4:,}* de capacidade"
                                      "\n\t*{7:,}* de experiência total"
                                      "\n\t*{8:,}* para o próximo nível"
                                      .format(level, char["vocation"].lower(), stats["hp"], stats["mp"], stats["cap"],
                                              char['name'], pronoun, stats["exp"], stats["exp_tnl"]), parse_mode='Markdown')
          else:
              yield from self.sender.sendMessage("Um {1} de nível *{0}* {1} tem:"
                                      "\n\t*{2:,}* HP"
                                      "\n\t*{3:,}* MP"
                                      "\n\t*{4:,}* de capacidade"
                                      "\n\t*{5:,}* de experiência total"
                                      "\n\t*{6:,}* para o próximo nível"
                                      .format(level, stats["vocation"], stats["hp"], stats["mp"], stats["cap"],
                                              stats["exp"], stats["exp_tnl"]), parse_mode='Markdown')
      else:
          yield from self.sender.sendMessage("Tem certeza que isso está certo?")      
    
    #blessings      
    if command.startswith('/blessing'):
      """Calculates the price of blessings at a specific level"""
      if param is None:
          yield from self.sender.sendMessage("Eu preciso de um nível para te dizer os preços das bênçãos. Exemplo:\n" \
                                             "`/blessing 120`", parse_mode='Markdown')
          return          
      try:
        level = int(param)
      except ValueError:
        yield from self.sender.sendMessage('O nível precisa ser um número!', parse_mode='Markdown')
        return            
      if level < 1:
          yield from self.sender.sendMessage("Bela tentativa... Agora me diga um número válido.")
          return
      price = 200 * (level - 20)
      if level <= 30:
          price = 2000
      if level >= 120:
          price = 20000
      inquisition = ""
      if level >= 100:
          inquisition = "\nA benção da _Inquisition_ custa *{0:,}* moedas de ouro (gp).".format(int(price*5*1.1))
      yield from self.sender.sendMessage(
              "Neste nível, você pagará *{0:,}* moedas de ouro (gp) por benção, totalizando *{1:,}* moedas de ouro (gp).{2}"
              .format(price, price*5, inquisition), parse_mode='Markdown')     

    #spell      
    if command.startswith('/spell'):
      """Tells you information about a certain spell."""
      if param is None:
          yield from self.sender.sendMessage("Diga-me o nome ou as palavras de um feitiço. Exemplo:\n" \
                                             "`/spell exura`", parse_mode='Markdown')
          return
      spell = get_spell(param)

      if spell is None:
          yield from self.sender.sendMessage("Eu não conheço nenhum feitiço com este nome ou com estas palavras.")
          return

      if type(spell) is list:
          embed = "\n".join(spell)
          embed = "Eu não pude encontrar um feitiço com este nome. Talvez você quis dizer algum destes?\n" + embed
          yield from self.sender.sendMessage(embed)
          return

      # Attach item's image only if the bot has permissions
      filename = spell['name'] + ".png"
      while os.path.isfile(filename):
          filename = "_" + filename
      with open(filename, "w+b") as f:
          f.write(bytearray(spell['image']))
          f.close()

      with open(filename, "r+b") as f:
          yield from self.sender.sendPhoto(f)
          f.close()
      os.remove(filename)
      
      #long = ctx.message.channel.is_private or ctx.message.channel.name == ask_channel_name
      #embed = self.get_spell_embed(ctx, spell, long)
      
      yield from self.sender.sendMessage('Ainda não está pronta a funcionalidade de listar informações do feitiço')              
        
  @asyncio.coroutine
  def time(self):
      """Displays tibia server's time and time until server save"""
      offset = get_tibia_time_zone() - get_local_timezone()
      tibia_time = datetime.now()+timedelta(hours=offset)
      server_save = tibia_time
      if tibia_time.hour >= 10:
          server_save += timedelta(days=1)
      server_save = server_save.replace(hour=10, minute=0, second=0, microsecond=0)
      time_until_ss = server_save - tibia_time
      hours, remainder = divmod(int(time_until_ss.total_seconds()), 3600)
      minutes, seconds = divmod(remainder, 60)

      timestrtibia = tibia_time.strftime("%H:%M")
      server_save_str = '{h} hours and {m} minutes'.format(h=hours, m=minutes)

      reply = "It's currently **{0}** in Tibia's servers.".format(timestrtibia)
      if display_brasilia_time:
          offsetbrasilia = get_brasilia_time_zone() - get_local_timezone()
          brasilia_time = datetime.now()+timedelta(hours=offsetbrasilia)
          timestrbrasilia = brasilia_time.strftime("%H:%M")
          reply += "\n**{0}** in Brazil (Brasilia).".format(timestrbrasilia)
      if display_sonora_time:
          offsetsonora = -7 - get_local_timezone()
          sonora_time = datetime.now()+timedelta(hours=offsetsonora)
          timestrsonora = sonora_time.strftime("%H:%M")
          reply += "\n**{0}** in Mexico (Sonora).".format(timestrsonora)
      reply += "\nServer save is in {0}.\nRashid is in **{1}** today.".format(server_save_str, get_rashid_city())
      yield from self.bot.say(reply)        

  @staticmethod
  def get_char_string(char) -> str:
      """Returns a formatted string containing a character's info."""
      if char == ERROR_NETWORK or char == ERROR_DOESNTEXIST:
          return char
      pronoun = "Ele"
      pronoun2 = "Sua"
      pronoun3 = "um"
      if char['gender'] == "female":
          pronoun = "Ela"
          pronoun2 = "Sua"
          pronoun3 = "uma"
      url = url_character + urllib.parse.quote(char["name"].encode('iso-8859-1'))
      reply_format = "[{1}]({9}) é um *{3}* nível {2} . {0} vive em *{4}* no mundo de *{5}*.{6}{7}{8}{10}"
      guild_format = "\n{0} é {4} __{1}__ de [{2}]({3})."
      married_format = "\n{0} é casado com [{1}]({2})."
      login_format = "\n{0} não se conecta por _{1}_."
      house_format = "\n{0} é dono de [{1}]({2}) em {3}."
      guild = ""
      married = ""
      house = ""
      login = "\n{0} *nunca* se conectou.".format(pronoun)
      if "guild" in char:
          guild_url = url_guild+urllib.parse.quote(char["guild"])
          guild = guild_format.format(pronoun, char['rank'], char['guild'], guild_url,pronoun3)
      if "married" in char:
          married_url = url_character + urllib.parse.quote(char["married"].encode('iso-8859-1'))
          married = married_format.format(pronoun, char['married'], married_url)
      if "house" in char:
          house_url = url_house.format(id=char["house_id"], world=char["world"])
          house = house_format.format(pronoun, char["house"], house_url, char["house_town"])
      if char['last_login'] is not None:
          last_login = parse_tibia_time(char['last_login'])
          now = datetime.now()    
          time_diff = now - last_login
          login = login_format.format(pronoun, get_time_diff(time_diff))

      reply = reply_format.format(pronoun, char['name'], char['level'], char['vocation'], char['residence'],
                                  char['world'], guild, married, login, url, house)
      if lite_mode:
          return reply
      # Insert any highscores this character holds
      for category in highscores_categories:
          if char.get(category, None):
              highscore_string = highscore_format[category].format(pronoun2, char[category], char[category+'_rank'])
              reply += "\n🏆 {0}".format(highscore_string)
      return reply        
  
  def on_close(self, ex):
    yield from self.sender.sendMessage('Fechou')

class ChatBox(telepot.aio.DelegatorBot):
  def __init__(self, token):
    super(ChatBox, self).__init__(token, [
        pave_event_space()(
            per_chat_id(), create_open, Tibia, timeout=10),
    ])

    

#TOKEN = sys.argv[1]  # get token from command-line
TOKEN = '344437874:AAEXStWb9DM3S6FhtWC-jlWULgv-1gyoWLU'
#TOKEN = '283648340:AAE6n-MG0ZEj_5rwBypeR1aN5yp7a7W7NwY'

#bot = ChatBox(TOKEN)
bot = telepot.aio.DelegatorBot(TOKEN, [
    pave_event_space()(
        per_chat_id(), create_open, Tibia, timeout=10),
])
loop = asyncio.get_event_loop()
loop.create_task(bot.message_loop())
print('Listening ...')

loop.run_forever()