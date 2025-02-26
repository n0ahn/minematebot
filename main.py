import os
import discord
from discord import app_commands
from discord.ui import Button, View
from dotenv import load_dotenv
import random
import asyncio
import requests

opus_path = "/opt/homebrew/Cellar/opus/1.5.2/lib/libopus.dylib"
if os.path.exists(opus_path):
    discord.opus.load_opus(opus_path)
    print("Opus succesfully loaded!")
else:
    print("Opus library not found!")


load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

@client.event
async def on_ready():
    await tree.sync()
    print(f'Successfully logged in as {client.user}')

@tree.command(
    name="help",
    description="Shows a list of all available commands"
)
async def help(interaction):
    embed = discord.Embed(
        title="📋   Help Menu",
        description="Here are all available commands:",
        color=discord.Color.blurple()
    )
    command_list = tree.get_commands()

    for cmd in command_list:
        embed.add_field(name=f"/{cmd.name}", value=cmd.description, inline=False)

    await interaction.response.send_message(embed=embed)


@tree.command(
    name="ping",
    description="Checks if the bot is online",
)
async def ping(interaction):
    responses = ["Pong!", "Hello!", "Connection established!", "Hello there!", "Yes, I'm online!", "Wh- What?", "*creeper sound* WAAAAAHH!", "Redstone signal received!"]
    response = random.choice(responses)
    await interaction.response.send_message(response)

@tree.command(
    name="musiclist",
    description="Shows a list of available Minecraft music discs and tracks."
)
async def musiclist(interaction: discord.Interaction):
    music_dir = "music/"
    if not os.path.exists(music_dir):
        await interaction.response.send_message("The music folder is missing!", ephemeral=True)
        return

    songs = [f[:-4] for f in os.listdir(music_dir) if f.endswith(".mp3")]
    songs.sort()
    
    if not songs:
        await interaction.response.send_message("No Minecraft songs found!", ephemeral=True)
        return
    
    items_per_page = 15
    pages = [songs[i:i + items_per_page] for i in range(0, len(songs), items_per_page)]
    
    class MusicListView(View):
        def __init__(self):
            super().__init__()
            self.current_page = 0
            
        async def update_embed(self, interaction):
            embed = discord.Embed(
                title="🎵   Available Minecraft Songs",
                description="\n".join(pages[self.current_page]),
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"Page {self.current_page + 1} of {len(pages)}")
            await interaction.response.edit_message(embed=embed, view=self)
        
        @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary, disabled=True)
        async def previous_page(self, interaction: discord.Interaction, button: Button):
            self.current_page -= 1
            self.next_page.disabled = False
            if self.current_page == 0:
                self.previous_page.disabled = True
            await self.update_embed(interaction)
            
        @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
        async def next_page(self, interaction: discord.Interaction, button: Button):
            self.current_page += 1
            self.previous_page.disabled = False
            if self.current_page == len(pages) - 1:
                self.next_page.disabled = True
            await self.update_embed(interaction)
    
    view = MusicListView()
    embed = discord.Embed(
        title="🎵   Available Minecraft Songs",
        description="\n".join(pages[0]),
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"Page 1 of {len(pages)}")
    
    await interaction.response.send_message(embed=embed, view=view)

music_queue = []
repeat_mode = False
shuffle_mode = False
music_dir = "music"

def get_music_tracks():
    if not os.path.exists(music_dir):
        return []
    return sorted([file[:-4] for file in os.listdir(music_dir) if file.endswith(".mp3")])

async def music_autocomplete(interaction: discord.Interaction, current: str):
    tracks = get_music_tracks()
    return [
        discord.app_commands.Choice(name=track, value=track)
        for track in tracks if current.lower() in track
    ][:25]

@tree.command(
    name="play",
    description="Plays Minecraft music/music disks"
)
@app_commands.autocomplete(track=music_autocomplete)
async def play(interaction: discord.Interaction, track: str):
    global repeat_mode, shuffle_mode
    if not interaction.user.voice:
        await interaction.response.send_message("You need to be in a voice channel!")
        return

    music_path = f"{music_dir}/{track}.mp3"
    if not os.path.exists(music_path):
        await interaction.response.send_message(f"❌ Track `{track}` not found! Use `/musiclist` to see available tracks.", ephemeral=True)
        return

    channel = interaction.user.voice.channel
    voice_client = interaction.guild.voice_client

    await interaction.response.defer()

    def play_next_song(error=None):
        if repeat_mode:
            play_song(track)
        elif shuffle_mode:
            next_track = random.choice(get_music_tracks())
            play_song(next_track)
        elif music_queue:
            next_track = music_queue.pop(0)
            play_song(next_track)

    def play_song(song):
        next_path = f"{music_dir}/{song}.mp3"
        if os.path.exists(next_path):
            if voice_client.is_playing():
                voice_client.stop()
            source = discord.FFmpegPCMAudio(next_path, executable="ffmpeg")
            voice_client.play(source, after=play_next_song)
            asyncio.create_task(interaction.followup.send(embed=discord.Embed(
                title=f"▶️   Now Playing: {song}",
                color=discord.Color.blue()
            )))

        else:
            asyncio.create_task(interaction.channel.send(f"❌ Track `{song}` was missing, skipping..."))
            play_next_song()

    if voice_client:
        play_song(track)
    else:
        voice_client = await channel.connect()
        play_song(track)

@tree.command(
        name="pause",
        description="Pauses the minecraft music playing"
)
async def pause(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.pause()
        pause_embed = discord.Embed(
            title="⏸️   Paused the minecraft music.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=pause_embed)
    else:
        await interaction.response.send_message("There is no music playing to pause.")

@tree.command(
        name="resume",
        description="Resumes the minecraft music that was paused"
)
async def resume(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_paused():
        voice_client.resume()
        resume_embed = discord.Embed(
            title="▶️   Resumed the minecraft music.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=resume_embed)
    else:
        await interaction.response.send_message("There is no paused music to resume.")

@tree.command(
    name="next",
    description= "Plays the next track in the queue"
)
async def next(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client

    if voice_client and voice_client.is_playing():
        voice_client.stop()
        skip_embed = discord.Embed(
            title="⏭️   Skipping to the next track...",
            color=discord.Color.yellow()
        )
        await interaction.response.send_message(embed=skip_embed)
    elif repeat_mode:
        voice_client.play()
    else:
        await interaction.response.send_message("There's no track playing to skip!", ephemeral=True)


repeat_mode = False
shuffle_mode = False

@tree.command(
    name="repeat",
    description="Turn repeat mode on/off"
)
async def repeat(interaction: discord.Interaction, state: str):
    global repeat_mode
    if state.lower() == "on":
        repeat_mode = True
        repeat_embed = discord.Embed (
            title="🔄   Repeat mode is now ON."
        )
        await interaction.response.send_message(embed=repeat_embed)
    elif state.lower() == "off":
        repeat_mode = False
        repeat_embed = discord.Embed (
            title="🔄   Repeat mode is now OFF."
        )
        await interaction.response.send_message(embed=repeat_embed)
    else:
        await interaction.response.send_message("Invalid state! Use `/repeat on` or `/repeat off`.", ephemeral=True)

@tree.command(
    name="shuffle",
    description="Turn shuffle mode on/off"
)
async def shuffle(interaction: discord.Interaction, state: str):
    global shuffle_mode
    if state.lower() == "on":
        shuffle_mode = True
        shuffle_embed = discord.Embed (
            title="🔀   Shuffle mode is now ON."
        )
        await interaction.response.send_message(embed=shuffle_embed)
    elif state.lower() == "off":
        shuffle_mode = False
        shuffle_embed = discord.Embed (
            title="🔀   Shuffle mode is now OFF."
        )
        await interaction.response.send_message(embed=shuffle_embed)
    else:
        await interaction.response.send_message("Invalid state! Use `/shuffle on` or `/shuffle off`.", ephemeral=True)


music_queue = []  

class QueueGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="queue", description="Manage the music queue")

    @app_commands.command(name="add", description="Adds a track to the music queue")
    async def queue_add(self, interaction: discord.Interaction, track: str):
        music_path = f"music/{track}.mp3"
        if not os.path.exists(music_path):
            await interaction.response.send_message(f"❌ Track `{track}` not found! Use `/musiclist` to see available tracks.", ephemeral=True)
            return

        music_queue.append(track)
        embed = discord.Embed(
            title="✅   Added to Queue",
            description=f"`{track}` has been added to the queue.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="remove", description="Removes a track from the music queue")
    async def queue_remove(self, interaction: discord.Interaction, track: str):
        if track in music_queue:
            music_queue.remove(track)
            embed = discord.Embed(
                title="🗑️   Removed from Queue",
                description=f"`{track}` has been removed from the queue.",
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("That track is not in the queue.", ephemeral=True)

    @app_commands.command(name="view", description="Displays the current music queue")
    async def queue_view(self, interaction: discord.Interaction):
        global repeat_mode, shuffle_mode
        if repeat_mode:
            await interaction.response.send_message("Repeat mode is ON. Turn it off to use the queue again.", ephemeral=False)
        elif shuffle_mode:
            await interaction.response.send_message("Shuffle mode is ON. Turn it off to use the queue again.", ephemeral=False)
        elif not music_queue:
            await interaction.response.send_message("The queue is currently empty.", ephemeral=False)
        else:
            embed = discord.Embed(
                title="🎶   Current Queue",
                description="\n".join([f"{i+1}. {song}" for i, song in enumerate(music_queue)]),
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed)
    @app_commands.command(name="clear", description="Clears the entire music queue")
    async def queue_clear(self, interaction: discord.Interaction):
        global music_queue
        music_queue.clear()
        await interaction.response.send_message("The queue has been cleared.", ephemeral=False)

tree.add_command(QueueGroup())

@tree.command(
        name="stop", 
        description="Stops the minecaft music playing"
        )
async def stop(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        stop_music = discord.Embed(
            title="🛑   Stopped music.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=stop_music)
    else:
        await interaction.response.send_message("I'm not in a voice channel!")

recipes_dir = "recipes"

def get_recipe_items():
    if not os.path.exists(recipes_dir):
        return []
    sorted_files = sorted(os.listdir(recipes_dir))
    return [file[6:-4].lower() for file in sorted_files if file.startswith("craft_")]

async def recipe_autocomplete(interaction: discord.Interaction, current: str):
    items = get_recipe_items()
    return [
        discord.app_commands.Choice(name=recipe, value=recipe)
        for recipe in items if current.lower() in recipe
    ][:25]  # Discord allows max 25 choices

@tree.command(
    name="recipe",
    description="Shows a recipe of a craftable item"
)
@discord.app_commands.autocomplete(item=recipe_autocomplete)
async def recipe(interaction: discord.Interaction, item: str):
    recipe_items = {file[6:-4].lower(): file for file in os.listdir(recipes_dir) if file.startswith("craft_")}

    if item.lower() not in recipe_items:
        await interaction.response.send_message(f"Recipe for '{item}' not found.")
        return

    recipe_image_path = os.path.join(recipes_dir, recipe_items[item.lower()])

    with open(recipe_image_path, "rb") as img_file:
        await interaction.response.send_message(file=discord.File(img_file, recipe_items[item.lower()]))


@tree.command (
    name="randomfact",
    description="Shows a random minecraft fact"
)
async def randomfact(interaction: discord.Interaction):
    facts = {
    "Creepers were created by accident when Notch tried to make a pig but messed up the dimensions.",
    "You can put a pumpkin on your head to avoid angering Endermen when looking at them.",
    "A day in Minecraft lasts 20 minutes in real-time.",
    "If you name a sheep 'jeb_' with a name tag, it will cycle through all wool colors.",
    "The End Portal frame cannot be broken in Survival mode, even with a pickaxe.",
    "Cats scare away Creepers, making them great pets for home protection.",
    "Despite their size, Ghasts make very quiet ambient sounds when idle.",
    "Wolves will attack any mob that harms their owner, except for Creepers.",
    "If you fall from a great height, you can survive by landing in water, even if it's just one block deep.",
    "Villagers have professions based on their job site block, such as a lectern for librarians.",
    "The first version of Minecraft was created in just six days.",
    "You can use honey blocks to reduce fall damage and move slower, useful for parkour.",
    "Pandas can have different personalities, like lazy, aggressive, and playful.",
    "Piglins love gold and won’t attack you if you wear at least one piece of gold armor.",
    "The Wither is the only mob that can break obsidian blocks with its explosions.",
    "The Far Lands, a bugged terrain generation from older versions, existed millions of blocks away from spawn.",
    "Axolotls will help players fight underwater mobs like Drowned and Guardians.",
    "In older versions, Zombies could turn villagers into Zombie Villagers without a cure.",
    "Shulkers shoot projectiles that cause the Levitation effect, making players float.",
    "The Ender Dragon heals itself using End Crystals on top of obsidian pillars.",
    "You can ride a pig using a saddle, but you need a carrot on a stick to control it.",
    "Tamed parrots will dance when music from a jukebox is playing nearby.",
    "You can use campfires to cook food without needing fuel, but it takes longer.",
    "Snow Golems leave a trail of snow wherever they walk, except in warm biomes.",
    "You can break a boat and still get the boat back, making them a reusable transport item.",
    "If lightning strikes a Creeper, it becomes a Charged Creeper with a much stronger explosion.",
    "A turtle shell helmet grants the player 10 extra seconds of water breathing.",
    "If a Skeleton kills a Creeper, the Creeper drops a music disc.",
    "Hoes are the fastest tool for breaking leaves, despite being intended for farming."
}
    random_fact = random.choice(facts)
    await interaction.response.send_message(random_fact)

client.run(TOKEN)