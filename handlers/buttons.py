import discord
from psql import execute

class BirthdaySetupButton(discord.ui.View):
    def __init__(self, interaction, channel, role):
        super().__init__(timeout=60)
        self.interaction = interaction
        self.channel = channel
        self.role = role
        self.value = None
    
    @discord.ui.button(label="Yes",style=discord.ButtonStyle.green)
    async def setup_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
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
        embed = discord.Embed(
            title="Setup Complete!",
            color=discord.Color(value=0xf8e7ef)
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
        
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Setup cancelled.", embed=None, view=None)
        self.value = False
        self.stop()

class BirthdayUpdateButton(discord.ui.View):
    def __init__(self, interaction, birthdate, timezone):
        super().__init__(timeout=60)
        self.interaction = interaction
        self.birthdate = birthdate
        self.timezone = timezone
        self.value = None
    
    @discord.ui.button(label="Yes",style=discord.ButtonStyle.green)
    async def update_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await execute("""
            UPDATE birthday_user
            SET birthdate = $1,
                timezone = $2,
                last_updated = CURRENT_TIMESTAMP
            WHERE guild_id = $4 AND user_id = $5
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
        
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Birthday Update Cancelled.", embed=None, view=None)
        self.value = False
        self.stop()
        