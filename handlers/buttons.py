import discord
from discord.ui import View, Button
from discord import Interaction, ButtonStyle, Embed, Color, Forbidden

class BirthdaySetupButton(View):
    def __init__(self, interaction, channel, role):
        super().__init__(timeout=60)
        self.interaction = interaction
        self.channel = channel
        self.role = role
        self.value = None
    
    @discord.ui.button(label="Yes",style=ButtonStyle.green)
    async def setup_callback(self, interaction: Interaction, button: Button):
        from psql import execute
        await execute("""
            INSERT INTO birthday_guild (guild_id, channel_id, role_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id)
            DO UPDATE SET channel_id = EXCLUDED.channel_id, role_id = EXCLUDED.role_id
        """,
            self.interaction.guild.id,
            self.channel.id,
            self.role.id if self.role else None
        )
        embed = Embed(
            title="Setup Complete!",
            color=Color(value=0xf8e7ef)
        )
        embed.add_field(
            name="Channel",
            value=f"Birthday messages will appear in {self.channel.mention}"
        )
        embed.add_field(
            name="Role",
            value=f"No Role Set" if not self.role else f'Notifying {self.role.mention} when birthdays appears'
        )
        await interaction.response.edit_message(content="✅ Overwritten successfully!", embed=embed, view=None)
        self.value = True
        self.stop()
        
    @discord.ui.button(label="Cancel", style=ButtonStyle.red)
    async def cancel(self, interaction: Interaction, button: Button):
        await interaction.response.edit_message(content="❌ Setup cancelled.", embed=None, view=None)
        self.value = False
        self.stop()

class BirthdayUpdateButton(View):
    def __init__(self, interaction, birthdate, timezone):
        super().__init__(timeout=60)
        self.interaction = interaction
        self.birthdate = birthdate
        self.timezone = timezone
        self.value = None
    
    @discord.ui.button(label="Yes",style=ButtonStyle.green)
    async def update_callback(self, interaction: Interaction, button: Button):
        from psql import execute
        await execute("""
            UPDATE birthday_user
            SET birthdate = $1,
                timezone = $2,
                last_updated = CURRENT_TIMESTAMP
            WHERE guild_id = $3 AND user_id = $4
        """,
            self.birthdate,
            self.timezone,
            self.interaction.guild.id,
            self.interaction.user.id
        )
        
        await interaction.response.edit_message(
            content="Your birthday has been updated successfully!",
            embed=None,
            view=None
        )
        
        self.value = True
        self.stop()
        
    @discord.ui.button(label="Cancel", style=ButtonStyle.red)
    async def cancel(self, interaction: Interaction, button: Button):
        await interaction.response.edit_message(content="❌ Birthday Update Cancelled.", embed=None, view=None)
        self.value = False
        self.stop()
        
class BugActionButton(View):
    def __init__(self, bot, reporter):
        super().__init__(timeout=None)
        self.bot = bot
        self.reporter = reporter
    
    @discord.ui.button(label="Accept",style=ButtonStyle.green)
    async def accept(self, interaction: Interaction, button: Button):
        await interaction.response.send_message("Bug marked as accepted.", ephemeral=False)
        await self.notify_user("Your bug report has been **accepted**.")
        await interaction.message.edit(view=ProgressQueueView(self.bot, self.reporter))
    
    @discord.ui.button(label="Reject", style=ButtonStyle.red)
    async def reject(self, interaction: Interaction, button: Button):
        await interaction.response.send_message("Bug marked as rejected.", ephemeral=False)
        await self.notify_user("Your bug report has been **rejected**.")
        await interaction.message.edit(view=None)
    
    async def notify_user(self, message: str):
        try:
            await self.reporter.send(message)
        except Forbidden:
            pass

class ProgressQueueView(View):
    def __init__(self, bot, reporter):
        super().__init__(timeout=None)
        self.bot = bot
        self.reporter = reporter

    @discord.ui.button(label="In Progress", style=ButtonStyle.blurple)
    async def in_progress(self, interaction: Interaction, button: Button):
        await interaction.response.send_message("Bug marked as In Progress.", ephemeral=False)
        await self.notify_user("Your bug report is now **In Progress**.")
        await interaction.message.edit(view=FinishedBugView(self.bot, self.reporter))

    @discord.ui.button(label="Queue", style=ButtonStyle.grey)
    async def queue(self, interaction: Interaction, button: Button):
        await interaction.response.send_message("Bug added to Queue.", ephemeral=False)
        await self.notify_user("Your bug report has been added to the **Queue**.")
        button.disabled = True
        await interaction.message.edit(view=self)

    async def notify_user(self, message: str):
        try:
            await self.reporter.send(message)
        except Forbidden:
            pass

class FinishedBugView(View):
    def __init__(self, bot, reporter):
        super().__init__(timeout=None)
        self.bot = bot
        self.reporter = reporter
    
    @discord.ui.button(label="Completed", style=ButtonStyle.green)
    async def completed(self, interaction: Interaction, button: Button):
        await interaction.response.send_message("Bug has been marked as completed", ephemeral=False)
        await self.notify_user("Your bug report has been **fixed**.")
        await interaction.message.edit(view=None)
    
    async def notify_user(self, message: str):
        try:
            await self.reporter.send(message)
        except Forbidden:
            pass
        
class FeatureRequestButton(View):
    def __init__(self, bot, reporter):
        super().__init__(timeout=None)
        self.bot = bot
        self.reporter = reporter
    
    @discord.ui.button(label="Accept",style=ButtonStyle.green)
    async def accept(self, interaction: Interaction, button: Button):
        await interaction.response.send_message("Feature marked as accepted.", ephemeral=False)
        await self.notify_user("Your feature request has been **accepted**.")
        await interaction.message.edit(view=FeatureQueueView(self.bot, self.reporter))
    
    @discord.ui.button(label="Reject", style=ButtonStyle.red)
    async def reject(self, interaction: Interaction, button: Button):
        await interaction.response.send_message("Feature marked as rejected.", ephemeral=False)
        await self.notify_user("Your feature request has been **rejected**.")
        await interaction.message.edit(view=None)
    
    async def notify_user(self, message: str):
        try:
            await self.reporter.send(message)
        except Forbidden:
            pass

class FeatureQueueView(View):
    def __init__(self, bot, reporter):
        super().__init__(timeout=None)
        self.bot = bot
        self.reporter = reporter

    @discord.ui.button(label="In Progress", style=ButtonStyle.blurple)
    async def in_progress(self, interaction: Interaction, button: Button):
        await interaction.response.send_message("Feature marked as In Progress.", ephemeral=False)
        await self.notify_user("Your feature request is now **In Progress**.")
        await interaction.message.edit(view=FinishedFeatureView(self.bot, self.reporter))

    @discord.ui.button(label="Queue", style=ButtonStyle.grey)
    async def queue(self, interaction: Interaction, button: Button):
        await interaction.response.send_message("Feature added to Queue.", ephemeral=False)
        await self.notify_user("Your feature request has been added to the **Queue**.")
        button.disabled = True
        await interaction.message.edit(view=self)

    async def notify_user(self, message: str):
        try:
            await self.reporter.send(message)
        except Forbidden:
            pass

class FinishedFeatureView(View):
    def __init__(self, bot, reporter):
        super().__init__(timeout=None)
        self.bot = bot
        self.reporter = reporter
    
    @discord.ui.button(label="Completed", style=ButtonStyle.green)
    async def completed(self, interaction: Interaction, button: Button):
        await interaction.response.send_message("Feature has been marked as completed", ephemeral=False)
        await self.notify_user("Your feature request has been **added**.")
        await interaction.message.edit(view=None)
    
    async def notify_user(self, message: str):
        try:
            await self.reporter.send(message)
        except Forbidden:
            pass
        
class PaginatorTextView(View):
    def __init__(self, interaction: Interaction, pages: list[Embed]):
        super().__init__(timeout=60)
        self.pages = pages
        self.current = 0
        
        @discord.ui.button(label='⏮️', style=ButtonStyle.grey)
        async def previous(self, interaction: Interaction, button: Button):
            if self.current > 0:
                self.current -= 1
                await interaction.response.edit_message(content=self.pages[self.current], view=self)
                
        @discord.ui.button(label='⏭️', style=ButtonStyle.grey)
        async def next(self, interaction: Interaction, button: Button):
            if self.current < len(self.pages) - 1:
                self.current += 1
                await interaction.response.edit_message(content=self.pages[self.current], view=self)
                
class PaginatorEmbedView(View):
    def __init__(self, interaction: Interaction, pages: list[Embed]):
        super().__init__(timeout=60)
        self.pages = pages
        self.current = 0
        
        @discord.ui.button(label='⏮️', style=ButtonStyle.grey)
        async def previous(self, interaction: Interaction, button: Button):
            if self.current > 0:
                self.current -= 1
                await interaction.response.edit_message(embed=self.pages[self.current], view=self)
                
        @discord.ui.button(label='⏭️', style=ButtonStyle.grey)
        async def next(self, interaction: Interaction, button: Button):
            if self.current < len(self.pages) - 1:
                self.current += 1
                await interaction.response.edit_message(embed=self.pages[self.current], view=self)