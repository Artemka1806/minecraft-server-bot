import datetime
import logging
import os

import disnake
from disnake import TextInputStyle
from disnake.ext import commands
from dotenv import load_dotenv
from umongo import Document, fields
from umongo.frameworks import MotorAsyncIOInstance
from motor.motor_asyncio import AsyncIOMotorClient
from mcrcon import MCRcon

logging.basicConfig(level=logging.INFO)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
VERIFICATION_CHANNEL_ID = int(os.getenv("VERIFICATION_CHANNEL_ID"))
ROLE_ID = int(os.getenv("ROLE_ID"))
MONGO_URI = os.getenv("MONGO_URI")
RCON_IP = os.getenv("RCON_IP")
RCON_PORT = int(os.getenv("RCON_PORT"))
RCON_PASSWORD = os.getenv("RCON_PASSWORD")

client = AsyncIOMotorClient(MONGO_URI)
db = client.data

instance = MotorAsyncIOInstance()
instance.set_db(db)

bot = commands.Bot(intents=disnake.Intents.default(), sync_commands_debug=True)


@instance.register
class User(Document):
    discord_id = fields.IntegerField(unique=True)
    discord_username = fields.StringField(allow_none=True)
    minecraft_nickname = fields.StringField()
    created_at = fields.DateTimeField(default=datetime.datetime.utcnow)


class VerifyModal(disnake.ui.Modal):
    def __init__(self):
        components = [
            disnake.ui.TextInput(
                label="Нік в Minecraft",
                placeholder="SuperKiller228",
                custom_id="nickname",
                style=TextInputStyle.short,
                max_length=50,
            ),
        ]
        super().__init__(title="Верифікація", components=components)

    
    async def callback(self, inter: disnake.ModalInteraction):
        data = inter.text_values.items()
        data = {key: value for key, value in data}

        user = User(discord_id=inter.author.id, discord_username=inter.author.discriminator, minecraft_nickname=data["nickname"])
        await user.commit()

        embed=disnake.Embed(title="Новий запит на приєднання", color=0x00ff40)
        embed.add_field(name="Нік в грі", value=data["nickname"], inline=False)
        embed.add_field(name="Юзер на сервері", value=f"<@{inter.author.id}>", inline=False)

        channel = bot.get_channel(VERIFICATION_CHANNEL_ID)
        if channel:
            await channel.send(embed=embed, components=[
                disnake.ui.Button(label="Підтвердити", style=disnake.ButtonStyle.success, custom_id=f"confirm::{inter.author.id}::{data['nickname']}"),
                disnake.ui.Button(label="Відхилити", style=disnake.ButtonStyle.danger, custom_id=f"decline::{inter.author.id}::{data['nickname']}"),
            ])
        await inter.response.send_message("Вашу заявку подано на розгляд адміністрації", ephemeral=True)


@bot.event
async def on_ready():
    logging.info(f"Bot is ready. Logged in as {bot.user}")


@bot.slash_command(default_member_permissions=disnake.Permissions(administrator=True), guild_ids=[GUILD_ID])
async def verify_message(inter):
    """Відправляє повідомлення для верифікації"""
    await inter.response.send_message("Для верифікації натисніть на кнопку нижче", components=[
            disnake.ui.Button(label="Верифікуватися", style=disnake.ButtonStyle.success, custom_id="verify"),
        ])


@bot.slash_command(default_member_permissions=disnake.Permissions(administrator=True), guild_ids=[GUILD_ID])
async def purge(inter, nickname: str):
    """Видаляє користувача з бд та з whitelist"""
    await inter.response.defer(ephemeral=True)
    user = await User.find_one({"minecraft_nickname": nickname})
    if user:
        await user.delete()
    command = f"easywhitelist remove {nickname}"
    with MCRcon(RCON_IP, RCON_PASSWORD, port=RCON_PORT) as rcon:
        response = rcon.command(command)
        await inter.edit_original_response(content=f"`{command}`\n```{response}```")

@bot.listen("on_button_click")
async def help_listener(inter: disnake.MessageInteraction):
    if inter.component.custom_id == "verify":
        user = await User.find_one({"discord_id": inter.author.id})
        if user:
            await inter.response.send_message("Ви вже подавали заявку на верифікацію", ephemeral=True)
        else:
            await inter.response.send_modal(VerifyModal())
    
    if inter.component.custom_id.startswith("confirm"):
        await inter.message.delete()
        await inter.response.defer()
        user_id, nickname = inter.component.custom_id.split("::")[1:]
        command = f"easywhitelist add {nickname}"
        with MCRcon(RCON_IP, RCON_PASSWORD, port=RCON_PORT) as rcon:
            response = rcon.command(command)
            channel = bot.get_channel(VERIFICATION_CHANNEL_ID)
            if channel:
                await channel.send(f"`{command}`\n```{response}```")

        user = await inter.guild.fetch_member(int(user_id))
        await user.add_roles(inter.guild.get_role(ROLE_ID))
        await user.send(f"Ваша заявка на верифікацію була підтверджена. Ваш нік: {nickname}")

    if inter.component.custom_id.startswith("decline"):
        await inter.message.delete()
        await inter.response.defer()
        user_id, nickname = inter.component.custom_id.split("::")[1:]
        user = await inter.guild.fetch_member(int(user_id))
        await user.send(f"Ваша заявка на верифікацію була відхилена. Ваш нік: {nickname}")


bot.run(BOT_TOKEN)
