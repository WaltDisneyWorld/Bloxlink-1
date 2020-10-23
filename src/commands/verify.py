from resources.structures.Bloxlink import Bloxlink # pylint: disable=import-error
from discord.errors import Forbidden, NotFound
from discord import Embed, Object
from os import environ as env
from resources.exceptions import Message, UserNotVerified, Error, RobloxNotFound, BloxlinkBypass, Blacklisted # pylint: disable=import-error
from resources.constants import (DEFAULTS, NICKNAME_TEMPLATES, CACHE_CLEAR, TIP_CHANCES, GREEN_COLOR, ORANGE_COLOR, # pylint: disable=import-error
                                BROWN_COLOR, ARROW, VERIFY_URL, ACCOUNT_SETTINGS_URL) # pylint: disable=import-error
from aiotrello.exceptions import TrelloNotFound, TrelloUnauthorized, TrelloBadRequest
from resources.secrets import TRELLO # pylint: disable=import-error
import random

verify_as, update_member, get_user, get_nickname, get_roblox_id, parse_accounts, unverify_member, format_update_embed = Bloxlink.get_module("roblox", attrs=["verify_as", "update_member", "get_user", "get_nickname", "get_roblox_id", "parse_accounts", "unverify_member", "format_update_embed"])
get_options = Bloxlink.get_module("trello", attrs="get_options")
post_event = Bloxlink.get_module("utils", attrs=["post_event"])
get_features = Bloxlink.get_module("premium", attrs=["get_features"])


@Bloxlink.command
class VerifyCommand(Bloxlink.Module):
    """link your Roblox account to your Discord account and get your server roles"""

    def __init__(self):
        self.examples = ["add", "unlink", "view", "blox_link"]
        self.category = "Account"
        self.cooldown = 5
        self.aliases = ["getrole", "getroles"]


    @staticmethod
    async def validate_username(message, content):
        try:
            roblox_id, username = await get_roblox_id(content)
        except RobloxNotFound:
            return None, "There was no Roblox account found with that username. Please try again."

        return username

    @Bloxlink.flags
    async def __main__(self, CommandArgs):
        trello_board = CommandArgs.trello_board
        guild_data = CommandArgs.guild_data
        guild = CommandArgs.message.guild
        author = CommandArgs.message.author
        response = CommandArgs.response
        prefix = CommandArgs.prefix

        if CommandArgs.flags.get("add") or CommandArgs.flags.get("verify") or CommandArgs.flags.get("force"):
            await CommandArgs.response.error(f"``{CommandArgs.prefix}verify --force`` is deprecated and will be removed in a future version of Bloxlink. "
                                             f"Please use ``{prefix}verify add`` instead.")

            return await self.add(CommandArgs)

        if CommandArgs.real_command_name in ("getrole", "getroles"):
            CommandArgs.string_args = []

        donator_profile, _ = await get_features(Object(id=guild.owner_id), guild=guild)
        premium = donator_profile.features.get("premium")

        if not premium:
            donator_profile, _ = await get_features(author)
            premium = donator_profile.features.get("premium")

        trello_options = {}

        if trello_board:
            trello_options, _ = await get_options(trello_board)
            guild_data.update(trello_options)

        #async with response.loading():
        try:
            added, removed, nickname, errors, roblox_user = await update_member(
                CommandArgs.message.author,
                guild                = guild,
                guild_data           = guild_data,
                roles                = True,
                nickname             = True,
                trello_board         = CommandArgs.trello_board,
                author_data          = await self.r.db("bloxlink").table("users").get(str(author.id)).run(),
                given_trello_options = True,
                cache                = not premium,
                response             = response,
                dm                   = False)

        except BloxlinkBypass:
            raise Message("Since you have the ``Bloxlink Bypass`` role, I was unable to update your roles/nickname.", type="info")

        except Blacklisted as b:
            if str(b):
                raise Error(f"{author.mention} has an active restriction for: ``{b}``")
            else:
                raise Error(f"{author.mention} has an active restriction from Bloxlink.")

        except UserNotVerified:
            await self.add(CommandArgs)
        else:
            welcome_message, embed = await format_update_embed(roblox_user, prefix, added, removed, errors, author, guild_data, premium)

            await response.send(content=welcome_message, embed=embed)

            await post_event(guild, guild_data, "verification", f"{author.mention} has **verified** as ``{roblox_user.username}``.", GREEN_COLOR)


    @Bloxlink.subcommand()
    async def add(self, CommandArgs):
        """link a new account to Bloxlink"""

        await CommandArgs.response.reply(f"to verify with Bloxlink, please visit our website at <{VERIFY_URL}>. It won't take long!\nStuck? "
                                          "See this video: <https://www.youtube.com/watch?v=hq496NmQ9GU>")


    @Bloxlink.subcommand(permissions=Bloxlink.Permissions().build("BLOXLINK_MANAGER"))
    async def customize(self, CommandArgs):
        """customize the behavior of !verify"""

        # TODO: able to set: "forced groups"

        prefix = CommandArgs.prefix
        response = CommandArgs.response

        author = CommandArgs.message.author

        guild = CommandArgs.message.guild
        guild_data = CommandArgs.guild_data


        choice = (await CommandArgs.prompt([{
            "prompt": "Which option would you like to change?\nOptions: ``(welcomeMessage)``",
            "name": "choice",
            "type": "choice",
            "choices": ("welcomeMessage",)
        }]))["choice"]


        trello_board = CommandArgs.trello_board
        card = None

        if trello_board:
            options_trello_data, trello_binds_list = await get_options(trello_board, return_cards=True)
            options_trello_find = options_trello_data.get(choice)

            if options_trello_find:
                card = options_trello_find[1]

        if choice == "welcomeMessage":
            welcome_message = (await CommandArgs.prompt([{
                "prompt": f"What would you like your welcome message to be? This will be shown in ``{prefix}verify`` messages.\nYou may "
                          f"use these templates: ```{NICKNAME_TEMPLATES}```",
                "name": "welcome_message",
                "formatting": False,
                "max": 1500
            }]))["welcome_message"]

            if trello_board and trello_binds_list:
                try:
                    if card:
                        if card.name == choice:
                            await card.edit(name="welcomeMessage", desc=welcome_message)
                    else:
                        trello_settings_list = await trello_board.get_list(lambda L: L.name == "Bloxlink Settings") \
                                            or await trello_board.create_list(name="Bloxlink Settings")

                        await trello_settings_list.create_card(name="welcomeMessage", desc=welcome_message)

                    await trello_binds_list.sync(card_limit=TRELLO["CARD_LIMIT"])

                except TrelloUnauthorized:
                    await response.error("In order for me to edit your Trello settings, please add ``@bloxlink`` to your "
                                         "Trello board.")

                except (TrelloNotFound, TrelloBadRequest):
                    pass

            await self.r.table("guilds").insert({
                "id": str(guild.id),
                "welcomeMessage": welcome_message
            }, conflict="update").run()

        await post_event(guild, guild_data, "configuration", f"{author.mention} has **changed** the ``{choice}``.", BROWN_COLOR)

        raise Message(f"Successfully saved your new ``{choice}``!", type="success")


    @staticmethod
    @Bloxlink.subcommand()
    async def view(CommandArgs):
        """view your linked account(s)"""

        author = CommandArgs.message.author
        response = CommandArgs.response

        try:
            primary_account, accounts = await get_user("username", author=author, everything=False, basic_details=True)
        except UserNotVerified:
            raise Message("You have no accounts linked to Bloxlink!", type="silly")
        else:
            accounts = list(accounts)

            parsed_accounts = await parse_accounts(accounts, reverse_search=True)
            parsed_accounts_str = []
            primary_account_str = "No primary account set"

            for roblox_username, roblox_data in parsed_accounts.items():
                if roblox_data[1]:
                    username_str = []

                    for discord_account in roblox_data[1]:
                        username_str.append(f"{discord_account} ({discord_account.id})")

                    username_str = ", ".join(username_str)

                    if primary_account and roblox_username == primary_account.username:
                        primary_account_str = f"**{roblox_username}** {ARROW} {username_str}"
                    else:
                        parsed_accounts_str.append(f"**{roblox_username}** {ARROW} {username_str}")

                else:
                    parsed_accounts_str.append(f"**{roblox_username}**")

            parsed_accounts_str = "\n".join(parsed_accounts_str)


            embed = Embed(title="Linked Roblox Accounts")
            embed.add_field(name="Primary Account", value=primary_account_str)
            embed.add_field(name="Secondary Accounts", value=parsed_accounts_str or "No secondary account saved")
            embed.set_author(name=author, icon_url=author.avatar_url)

            await response.send(embed=embed, dm=True, strict_post=True)

    @staticmethod
    @Bloxlink.subcommand()
    async def unlink(CommandArgs):
        """unlink an account from Bloxlink"""

        await CommandArgs.response.reply(f"to manage your accounts, please visit our website: <{ACCOUNT_SETTINGS_URL}>")
