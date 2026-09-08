import os
import discord
from discord.ext import commands
from discord.ui import Button, View
from dotenv import load_dotenv
import random
import asyncio
import sys
import json
from mcstatus import JavaServer
import re

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

script_dir = os.path.dirname(os.path.abspath(__file__))

if sys.platform == 'darwin':
    opus_path = os.path.join(script_dir, 'libopus.0.dylib')
    ffmpeg_executable = os.path.join(script_dir, "ffmpeg-mac")
elif sys.platform.startswith('linux'):
    opus_path = os.path.join(script_dir, 'libopus.so.0')
    ffmpeg_executable = os.path.join(script_dir, "ffmpeg-linux")
else:
    opus_path = None
    ffmpeg_executable = "ffmpeg"

if opus_path and os.path.exists(opus_path):
    try:
        discord.opus.load_opus(opus_path)
        print(f"Opus successfully loaded from: {opus_path}")
    except Exception as e:
        print(f"Failed to load Opus from {opus_path}: {e}")
        print("Voice commands may not work correctly.")
else:
    print(f"Opus library not found at {opus_path}! Voice commands will not work.")
    print("Please ensure the library is in the same directory as your bot's script.")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

music_queue = []
repeat_mode = False
shuffle_mode = False
music_dir = "music"
recipes_dir = "recipes"
current_text_channel = None

def load_data():
    try:
        with open('data.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("Error: data.json file not found!")
        return {}
    except json.JSONDecodeError:
        print("Error: Could not decode JSON from data.json. Please check the file for syntax errors.")
        return {}
    
DATA = load_data()

@bot.event
async def on_command_error(ctx, error):
    print(f"An error occurred with command: {ctx.command}")
    print(f"Error type: {type(error)}")
    print(f"Error details: {error}")
    
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(f"❌ I'm sorry, but I do not have the `{', '.join(error.missing_permissions)}` permission to do that.", ephemeral=True)
    elif isinstance(error, commands.MissingRole):
        await ctx.send(f"❌ You are missing the `{error.missing_role}` role required to use this command.", ephemeral=True)
    elif isinstance(error, commands.Forbidden):
        await ctx.send("❌ I was forbidden from doing that. Please check my role permissions and hierarchy.", ephemeral=True)
    elif isinstance(error, commands.CommandInvokeError):
        await ctx.send(f"An unexpected error occurred: {error.original}", ephemeral=True)
    elif isinstance(error, commands.NotOwner):
        await ctx.send("❌ This command is for the bot owner only.", ephemeral=True)
    else:
        await ctx.send(f"An unhandled error occurred.", ephemeral=True)
        raise error

def get_music_tracks():
    if not os.path.exists(music_dir):
        return []
    return sorted([file[:-4] for file in os.listdir(music_dir) if file.endswith(".mp3")])

def get_recipe_items():
    if not os.path.exists(recipes_dir):
        return []
    sorted_files = sorted(os.listdir(recipes_dir))
    return [file[6:-4].lower() for file in sorted_files if file.startswith("craft_")]

async def play_song(song):
    voice_client = bot.voice_clients[0]
    next_path = f"{music_dir}/{song}.mp3"
    
    if os.path.exists(next_path):
        if voice_client.is_playing():
            voice_client.stop()
        
        source = discord.FFmpegPCMAudio(next_path, executable=ffmpeg_executable)
        voice_client.play(source, after=play_next_song)
    else:
        if current_text_channel:
            await current_text_channel.send(f"❌ Track `{song}` was missing, skipping...")
        play_next_song()

def play_next_song(error=None):
    voice_client = bot.voice_clients[0]
    global music_queue, repeat_mode, shuffle_mode, current_text_channel

    if error:
        print(f'Player error: {error}')
        if current_text_channel:
            asyncio.run_coroutine_threadsafe(
                current_text_channel.send("An error occurred while playing the track."),
                bot.loop
            )

    if repeat_mode:
        last_track = voice_client.source.original.split('/')[-1].replace('.mp3', '')
        asyncio.run_coroutine_threadsafe(play_song(last_track), bot.loop)
    elif shuffle_mode:
        next_track = random.choice(get_music_tracks())
        asyncio.run_coroutine_threadsafe(play_song(next_track), bot.loop)
    elif music_queue:
        next_track = music_queue.pop(0)
        asyncio.run_coroutine_threadsafe(play_song(next_track), bot.loop)

@bot.event
async def on_ready():
    print(f'Successfully logged in as {bot.user}')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s).")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

class MinecraftBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(
        name="help",
        description="Shows a list of all available commands"
    )
    async def help_command(self, ctx):
        all_commands = self.bot.tree.get_commands()
        items_per_page = 10
        pages = [all_commands[i:i + items_per_page] for i in range(0, len(all_commands), items_per_page)]
        
        class HelpView(View):
            def __init__(self, pages):
                super().__init__()
                self.pages = pages
                self.current_page = 0
                
            async def update_embed(self, message):
                embed = discord.Embed(
                    title="📋   Help Menu",
                    description="Here are all available commands:",
                    color=discord.Color.blurple()
                )
                
                for cmd in self.pages[self.current_page]:
                    embed.add_field(name=f"/{cmd.name}", value=cmd.description or "No description provided.", inline=False)
                    
                embed.set_footer(text=f"Page {self.current_page + 1} of {len(self.pages)}")
                self.previous_page.disabled = self.current_page == 0
                self.next_page.disabled = self.current_page == len(self.pages) - 1
                await message.edit(embed=embed, view=self)
            
            @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary, disabled=True)
            async def previous_page(self, interaction: discord.Interaction, button: Button):
                if self.current_page > 0:
                    self.current_page -= 1
                    await self.update_embed(interaction.message)
                    await interaction.response.defer()
                
            @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
            async def next_page(self, interaction: discord.Interaction, button: Button):
                if self.current_page < len(self.pages) - 1:
                    self.current_page += 1
                    await self.update_embed(interaction.message)
                    await interaction.response.defer()

        view = HelpView(pages)
        initial_embed = discord.Embed(
            title="📋   Help Menu",
            description="Here are all available commands:",
            color=discord.Color.blurple()
        )
        
        for cmd in pages[0]:
            initial_embed.add_field(name=f"/{cmd.name}", value=cmd.description or "No description provided.", inline=False)
            
        initial_embed.set_footer(text=f"Page 1 of {len(pages)}")
        
        await ctx.send(embed=initial_embed, view=view)

    @commands.hybrid_command(
        name="ping",
        description="Checks if the bot is online",
    )
    async def ping_command(self, ctx):
        responses = ["Pong!", "Hello!", "Connection established!", "Hello there!", "Yes, I'm online!", "Wh- What?", "*creeper sound* WAAAAAHH!", "Redstone signal received!"]
        response = random.choice(responses)
        await ctx.send(response)

    @commands.hybrid_command(
        name="randomfact",
        description="Shows a random minecraft fact"
    )
    async def randomfact_command(self, ctx):
        facts = DATA.get("facts", [])
        if not facts:
            await ctx.send("No facts found! The `data.json` file may be missing or empty.")
            return
            
        random_fact = random.choice(facts)
        await ctx.send(random_fact)

    @commands.hybrid_command(
        name="recipe",
        description="Shows a recipe of a craftable item"
    )
    async def recipe_command(self, ctx, item: str):
        if not os.path.exists(recipes_dir):
            await ctx.send("The recipes folder is missing!")
            return

        recipe_items = {file[6:-4].lower(): file for file in os.listdir(recipes_dir) if file.startswith("craft_")}

        if item.lower() not in recipe_items:
            await ctx.send(f"Recipe for '{item}' not found.")
            return

        recipe_image_path = os.path.join(recipes_dir, recipe_items[item.lower()])

        with open(recipe_image_path, "rb") as img_file:
            await ctx.send(file=discord.File(img_file, recipe_items[item.lower()]))

    @recipe_command.autocomplete("item")
    async def recipe_autocomplete(self, interaction: discord.Interaction, current: str):
        recipe_list = get_recipe_items()
        return [
            discord.app_commands.Choice(name=item, value=item)
            for item in recipe_list if current.lower() in item.lower()
        ][:25]

    @commands.hybrid_command(
        name="musiclist",
        description="Shows a list of available Minecraft music discs and tracks."
    )
    async def musiclist_command(self, ctx):
        if not os.path.exists(music_dir):
            await ctx.send("The music folder is missing!")
            return

        songs = [f[:-4] for f in os.listdir(music_dir) if f.endswith(".mp3")]
        songs.sort()
        
        if not songs:
            await ctx.send("No Minecraft songs found!")
            return
        
        items_per_page = 15
        pages = [songs[i:i + items_per_page] for i in range(0, len(songs), items_per_page)]
        
        class MusicListView(View):
            def __init__(self, pages):
                super().__init__()
                self.pages = pages
                self.current_page = 0
                
            async def update_embed(self, message):
                embed = discord.Embed(
                    title="🎵   Available Minecraft Songs",
                    description="\n".join(self.pages[self.current_page]),
                    color=discord.Color.blue()
                )
                embed.set_footer(text=f"Page {self.current_page + 1} of {len(self.pages)}")
                self.previous_page.disabled = self.current_page == 0
                self.next_page.disabled = self.current_page == len(self.pages) - 1
                await message.edit(embed=embed, view=self)
            
            @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary, disabled=True)
            async def previous_page(self, interaction: discord.Interaction, button: Button):
                if self.current_page > 0:
                    self.current_page -= 1
                    await self.update_embed(interaction.message)
                    await interaction.response.defer()
                
            @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
            async def next_page(self, interaction: discord.Interaction, button: Button):
                if self.current_page < len(self.pages) - 1:
                    self.current_page += 1
                    await self.update_embed(interaction.message)
                    await interaction.response.defer()

        view = MusicListView(pages)
        embed = discord.Embed(
            title="🎵   Available Minecraft Songs",
            description="\n".join(pages[0]),
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Page 1 of {len(pages)}")
        
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(
        name="play",
        description="Plays Minecraft music/music disks"
    )
    async def play_command(self, ctx, track: str):
        global music_queue, current_text_channel
        
        initial_message = await ctx.send("🎵 Please wait... preparing your music!")

        if not ctx.author.voice:
            await initial_message.edit(content="❌ You need to be in a voice channel!", embed=None)
            await asyncio.sleep(5)
            await initial_message.delete()
            return

        music_path = f"{music_dir}/{track}.mp3"
        if not os.path.exists(music_path):
            await initial_message.edit(content=f"❌ Track `{track}` not found! Use `/musiclist` to see available tracks.", embed=None)
            await asyncio.sleep(5)
            await initial_message.delete()
            return

        channel = ctx.author.voice.channel
        voice_client = ctx.voice_client

        current_text_channel = ctx.channel

        try:
            if not voice_client:
                voice_client = await channel.connect()
            
            await play_song(track)
            
            now_playing_embed = discord.Embed(
                title=f"▶️   Now Playing: {track}",
                color=discord.Color.blue()
            )
            await initial_message.edit(content=None, embed=now_playing_embed)
            
        except Exception as e:
            print(f"Error during play command: {e}")
            await initial_message.edit(content="An unexpected error occurred while trying to play the track.", embed=None)
            
    @play_command.autocomplete("track")
    async def play_autocomplete(self, interaction: discord.Interaction, current: str):
        songs = get_music_tracks()
        return [
            discord.app_commands.Choice(name=song, value=song)
            for song in songs if current.lower() in song.lower()
        ][:25]

    @commands.hybrid_command(
        name="pause",
        description="Pauses the minecraft music playing"
    )
    async def pause_command(self, ctx):
        voice_client = ctx.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            pause_embed = discord.Embed(
                title="⏸️   Paused the minecraft music.",
                color=discord.Color.orange()
            )
            await ctx.send(embed=pause_embed)
        else:
            await ctx.send("There is no music playing to pause.")

    @commands.hybrid_command(
        name="resume",
        description="Resumes the minecraft music that was paused"
    )
    async def resume_command(self, ctx):
        voice_client = ctx.voice_client
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            resume_embed = discord.Embed(
                title="▶️   Resumed the minecraft music.",
                color=discord.Color.green()
            )
            await ctx.send(embed=resume_embed)
        else:
            await ctx.send("There is no paused music to resume.")

    @commands.hybrid_command(
        name="next",
        description= "Plays the next track in the queue"
    )
    async def next_command(self, ctx):
        voice_client = ctx.voice_client
        global repeat_mode

        if voice_client and voice_client.is_playing():
            voice_client.stop()
            skip_embed = discord.Embed(
                title="⏭️   Skipping to the next track...",
                color=discord.Color.yellow()
            )
            await ctx.send(embed=skip_embed)
        elif repeat_mode:
            voice_client.stop()
            skip_embed = discord.Embed(
                title="⏭️   Skipping to the next track...",
                color=discord.Color.yellow()
            )
            await ctx.send(embed=skip_embed)
        else:
            await ctx.send("There's no track playing to skip!")

    @commands.hybrid_command(
        name="repeat",
        description="Turn repeat mode on/off"
    )
    @discord.app_commands.choices(state=[
        discord.app_commands.Choice(name='on', value='on'),
        discord.app_commands.Choice(name='off', value='off'),
    ])
    async def repeat_command(self, ctx, state: discord.app_commands.Choice[str]):
        global repeat_mode
        if state.value == "on":
            repeat_mode = True
            repeat_embed = discord.Embed(title="🔄   Repeat mode is now ON.")
            await ctx.send(embed=repeat_embed)
        elif state.value == "off":
            repeat_mode = False
            repeat_embed = discord.Embed(title="🔄   Repeat mode is now OFF.")
            await ctx.send(embed=repeat_embed)
        
    @commands.hybrid_command(
        name="shuffle",
        description="Turn shuffle mode on/off"
    )
    @discord.app_commands.choices(state=[
        discord.app_commands.Choice(name='on', value='on'),
        discord.app_commands.Choice(name='off', value='off'),
    ])
    async def shuffle_command(self, ctx, state: discord.app_commands.Choice[str]):
        global shuffle_mode
        if state.value == "on":
            shuffle_mode = True
            shuffle_embed = discord.Embed(title="🔀   Shuffle mode is now ON.")
            await ctx.send(embed=shuffle_embed)
        elif state.value == "off":
            shuffle_mode = False
            shuffle_embed = discord.Embed(title="🔀   Shuffle mode is now OFF.")
            await ctx.send(embed=shuffle_embed)

    @commands.hybrid_command(
        name="stop", 
        description="Stops the minecaft music playing"
    )
    async def stop_command(self, ctx):
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            stop_music = discord.Embed(
                title="🛑   Stopped music.",
                color=discord.Color.red()
            )
            await ctx.send(embed=stop_music)
        else:
            await ctx.send("I'm not in a voice channel!")
            
    @commands.hybrid_command(name="add", description="Adds a track to the music queue")
    async def queue_add(self, ctx, track: str):
        global music_queue
        music_path = f"{music_dir}/{track}.mp3"
        if not os.path.exists(music_path):
            await ctx.send(f"❌ Track `{track}` not found! Use `/musiclist` to see available tracks.")
            return

        music_queue.append(track)
        embed = discord.Embed(
            title="✅   Added to Queue",
            description=f"`{track}` has been added to the queue.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @queue_add.autocomplete("track")
    async def queue_add_autocomplete(self, interaction: discord.Interaction, current: str):
        songs = get_music_tracks()
        return [
            discord.app_commands.Choice(name=song, value=song)
            for song in songs if current.lower() in song.lower()
        ][:25]

    @commands.hybrid_command(name="remove", description="Removes a track from the music queue")
    async def queue_remove(self, ctx, track: str):
        global music_queue
        if track in music_queue:
            music_queue.remove(track)
            embed = discord.Embed(
                title="🗑️   Removed from Queue",
                description=f"`{track}` has been removed from the queue.",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send("That track is not in the queue.")
            
    @queue_remove.autocomplete("track")
    async def queue_remove_autocomplete(self, interaction: discord.Interaction, current: str):
        global music_queue
        return [
            discord.app_commands.Choice(name=song, value=song)
            for song in music_queue if current.lower() in song.lower()
        ][:25]

    @commands.hybrid_command(name="view", description="Displays the current music queue")
    async def queue_view(self, ctx):
        global repeat_mode, shuffle_mode, music_queue
        if repeat_mode:
            await ctx.send("Repeat mode is ON. Turn it off to use the queue again.")
        elif shuffle_mode:
            await ctx.send("Shuffle mode is ON. Turn it off to use the queue again.")
        elif not music_queue:
            await ctx.send("The queue is currently empty.")
        else:
            embed = discord.Embed(
                title="🎶   Current Queue",
                description="\n".join([f"{i+1}. {song}" for i, song in enumerate(music_queue)]),
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="maxenchanted",
        description="Shows the maximum enchantments for a Minecraft item."
    )
    async def max_enchanted_command(self, ctx, item: str):
        enchantment_data = DATA.get("enchantments", {})
        item_data = enchantment_data.get(item.lower())

        if not item_data:
            available_items = ", ".join(enchantment_data.keys())
            await ctx.send(f"❌ Item not found. Available items are: `{available_items}`", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"{item_data.get('emoji', '')} Max Enchantments for {item.replace('_', ' ').title()}",
            color=discord.Color.gold()
        )

        for enchant in item_data["enchants"]:
            name = enchant["name"]
            level = enchant["level"]
            note = enchant.get("note", "")
            display_name = f"{name}" if level == "I" else f"{name} {level}"

            embed.add_field(
                name=display_name,
                value=f"• {note}" if note else "",
                inline=False
            )
        
        await ctx.send(embed=embed)

    @max_enchanted_command.autocomplete("item")
    async def max_enchanted_autocomplete(self, interaction: discord.Interaction, current: str):
        enchantment_data = DATA.get("enchantments", {})
        choices = [
            discord.app_commands.Choice(name=item.replace("_", " ").title(), value=item)
            for item in enchantment_data.keys()
            if current.lower() in item
        ]
        return choices[:25]
        
    @commands.hybrid_command(
        name="tradingguide",
        description="Shows a guide for Minecraft villager trading."
    )
    async def tradingguide_command(self, ctx):
        file_path = "tradingguide.png"
        
        if not os.path.exists(file_path):
            await ctx.send("❌ Error: The trading guide image was not found!", ephemeral=True)
            return
            
        try:
            file = discord.File(file_path, filename="tradingguide.png")
            
            await ctx.send(file=file)
            
        except Exception as e:
            await ctx.send(f"An unexpected error occurred while sending the image: {e}")
    
    @commands.hybrid_command(
        name="serverinfo",
        description="Retrieves information about a Minecraft server."
    )
    async def serverinfo_command(self, ctx, ip: str):
        initial_message = await ctx.send("⛏️ Please wait... Fetching server information.")

        try:
            server = await JavaServer.async_lookup(ip)
            status = await server.async_status()
            
            embed = discord.Embed(
                title=f"Server Info for `{ip}`",
                color=discord.Color.green()
            )
            embed.add_field(name="Status", value="🟢 Online", inline=True)
            embed.add_field(name="Version", value=status.version.name, inline=True)
            embed.add_field(name="Players", value=f"{status.players.online}/{status.players.max}", inline=True)
            
            motd = ""
            if isinstance(status.description, dict) and "text" in status.description:
                motd = status.description["text"]
            elif isinstance(status.description, str):
                motd = status.description
            
            if motd:
                clean_motd = re.sub(r'§[0-9a-fk-or]', '', motd)
                embed.add_field(name="MOTD", value=clean_motd, inline=False)
            
            if status.players.sample:
                player_list = "\n".join([player.name for player in status.players.sample])
                embed.add_field(name="Some Players", value=f"```\n{player_list}\n```", inline=False)

            await initial_message.edit(content=None, embed=embed)

        except Exception as e:
            print(f"Error fetching server info for {ip}: {e}")
            error_embed = discord.Embed(
                title=f"Server Info for `{ip}`",
                description=f"❌ Could not retrieve server information. The server may be offline, the IP is incorrect, or it is not a Java Edition server.",
                color=discord.Color.red()
            )
            await initial_message.edit(content=None, embed=error_embed)

    @commands.hybrid_command(
        name="orelevel",
        description="Shows the perfect Y-level for finding a specific ore."
    )
    async def orelevel_command(self, ctx, ore: str):
        ore_data = DATA.get("ore_levels", {})
        item_data = ore_data.get(ore.lower())

        if not item_data:
            available_ores = ", ".join(ore_data.keys())
            await ctx.send(f"❌ Ore not found. Available ores are: `{available_ores}`", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"{item_data.get('emoji', '⛏️')} Perfect Level for {ore.title()}",
            color=discord.Color.blue()
        )
        embed.add_field(name="Perfect Y-Level", value=item_data["perfect_y"], inline=False)
        embed.add_field(name="Details", value=item_data["info"], inline=False)
        
        await ctx.send(embed=embed)

    @orelevel_command.autocomplete("ore")
    async def orelevel_autocomplete(self, interaction: discord.Interaction, current: str):
        ore_data = DATA.get("ore_levels", {})
        choices = [
            discord.app_commands.Choice(name=item.replace("_", " ").title(), value=item)
            for item in ore_data.keys()
            if current.lower() in item
        ]
        return choices[:25]
    
    @commands.hybrid_command(
        name="sync",
        description="Owner only: Syncs slash commands with Discord."
    )
    @commands.is_owner()
    async def sync_command(self, ctx):
        await ctx.defer()
        try:
            synced = await self.bot.tree.sync()
            await ctx.send(f"✅ Successfully synced {len(synced)} command(s).", ephemeral=True)
            print(f"Synced {len(synced)} command(s).")
        except Exception as e:
            await ctx.send(f"❌ Failed to sync commands: {e}", ephemeral=True)
            print(f"Failed to sync commands: {e}")

    @commands.hybrid_command(
        name="restart",
        description="Owner only: Restarts the bot process."
    )
    @commands.is_owner()
    async def restart_command(self, ctx):
        await ctx.send("🔄 Restarting the bot...")
        python = sys.executable
        os.execv(python, [python, "main.py"])

async def main():
    async with bot:
        await bot.add_cog(MinecraftBot(bot))
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
