from __future__ import annotations

import asyncio

import logging

import discord
import openai
from discord import app_commands
from discord.ext import commands

from src.constants import (
    ACTIVATE_BUILD_THREAD_PREFIX,
    MAX_ASSISTANT_LIST,
    MAX_CHARS_PER_REPLY_MSG,
    ADMIN_SERVER_ID,
)
from src.discord_cogs._utils import (
    search_assistants,
    should_block,
    split_into_shorter_messages,
    is_me
)
from src.models.assistant import AssistantCreate
from src.models.message import function_tool_to_dict
from src.discord_cogs.chat import FunctionSelectView
from src.openai_api.assistants import (
    create_assistant,
    delete_assistant,
    get_assistant,
    list_assistants,
    update_assistant,
)
from src.openai_api.files import (
    upload_file,
    create_vector_store,
    update_vector_store,
)
from src.openai_api.function_tools import get_available_functions

logger = logging.getLogger(__name__)


class Assistant(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="build")
    @app_commands.guilds(ADMIN_SERVER_ID)
    async def build(self, int: discord.Interaction, name: str):
        """Create an assistant"""
        try:
            # only support creating assistant in text channel
            if not isinstance(int.channel, discord.TextChannel):
                return

            # block servers not in allow list
            if should_block(guild=int.guild):
                return

            user = int.user
            logger.info(f"Build command by {user}")

            # Create embed
            embed = discord.Embed(
                description=f"<@{user.id}> wants to build an assistant! 🤖💬",
                color=discord.Color.blue(),
            )
            await int.response.send_message(embed=embed)

            # create the thread
            response = await int.original_response()
            thread = await response.create_thread(
                name=f"{ACTIVATE_BUILD_THREAD_PREFIX} - {name} - {user.name[:20]}",
                slowmode_delay=1,
                reason="gpt-bot",
                auto_archive_duration=60,
            )

            # Description
            await thread.send("What is the description of your assistant?")
            description = await self.bot.wait_for("message", check=lambda m: m.author == user)

            # Instructions
            await thread.send("What are the instructions for your assistant?")
            instructions = await self.bot.wait_for("message", check=lambda m: m.author == user)

            # Tools
            tools = []
            await thread.send("What are the tools for your assistant?")

            # File search
            retrieval_view = TrueFalseView()
            await thread.send("# File Search", view=retrieval_view)
            retrieval_value = False
            try:
                retrieval_value = await asyncio.wait_for(retrieval_view.value, timeout=180)
                if retrieval_value:
                    tools.append({"type": "file_search"})
            except asyncio.TimeoutError:
                await thread.send("Timed out waiting for button click")

            # Code interpreter
            code_interpreter_view = TrueFalseView()
            await thread.send(
                "# Code Interpreter", 
                view=code_interpreter_view
            )
            code_interpreter_value = False
            try:
                code_interpreter_value = await asyncio.wait_for(code_interpreter_view.value, timeout=180)
                if code_interpreter_value:
                    tools.append({"type": "code_interpreter"})
            except asyncio.TimeoutError:
                await thread.send("Timed out waiting for button click")
            
            # Function Calling
            # TODO: fix function selection
            function_calling_view = TrueFalseView()
            await thread.send("# Function Calling", view=function_calling_view)
            function_calling_value = False
            try:
                function_calling_value = await asyncio.wait_for(function_calling_view.value, timeout=180)
            except asyncio.TimeoutError:
                await thread.send("Timed out waiting for button click")
                
            if function_calling_value:
                view = FunctionSelectView(thread=thread)
                available_functions = get_available_functions()
                
                for func in available_functions:
                    view.selectMenu.add_option(
                        label=func["function"]["name"],
                        value=func["function"]["name"],
                        description=func["function"]["description"][0:min([100, len(func["function"]["description"])])],
                    )

                await thread.send("Select the function:", view=view)
            
                try:
                    await asyncio.wait_for(view.wait(), timeout=180)
                    if view.selected_function:
                        func = next((f for f in available_functions if f["function"]["name"] == view.selected_function), None)
                        if func:
                            function_tool_dict = function_tool_to_dict(func)
                            tools.append(function_tool_dict)
                            await thread.send("Function was added to the assistant.")
                    else:
                        await thread.send("No function was added to the assistant.")
                except asyncio.TimeoutError:
                    await thread.send("Timed out waiting for function selection. No function was added to the assistant.")
            
            # File ids
            file_ids = list() # Default value
            # Upload the files if file search or code interpreter is enabled
            if retrieval_value or code_interpreter_value:
                file_upload_view = YesNoView(
                    {
                        "yes":"Please upload the files to be added to the assistant\n Send them at once if you want to add multiple files.",
                        "no": "No files will be added to the assistant."
                    }
                )

                await thread.send(
                    "Would you like to add files to the assistant?",
                    view=file_upload_view
                )
                
                file_upload_value = False
                try:
                    file_upload_value = await asyncio.wait_for(file_upload_view.value, timeout=180)
                except asyncio.TimeoutError:
                    await thread.send("Timed out waiting for button click. No files will be added to the assistant.")


                # Upload the files if the user wants to
                if file_upload_value:
                    message = await self.bot.wait_for("message", check=lambda m: m.author == user)
                    if message.attachments:
                        for attachment in message.attachments:
                            pseudo_file = ( 
                                attachment.filename, 
                                await attachment.read(), 
                                attachment.content_type
                            )
                            file_id = await upload_file(file=pseudo_file)
                            file_ids.append(file_id)
            else:
                file_ids = list() # Reset file_ids

            # Create Tool Resources if files are uploaded
            tool_resources = None
            if file_ids:
                tool_resources = dict()
                if retrieval_value:
                    tool_resources["file_search"] = dict(
                        vector_store_ids=list()
                    )
                    vector_store_name = f"{name} - Vector Store"
                    vector_store_id = await create_vector_store(
                        name=vector_store_name, 
                        file_ids=file_ids
                    )
                    tool_resources["file_search"]["vector_store_ids"].append(vector_store_id)
                if code_interpreter_value:
                    tool_resources["code_interpreter"] = dict(
                        file_ids=file_ids
                    )

            # Create the assistant
            created = await create_assistant(
                AssistantCreate(
                    name=name,
                    description=description.content,
                    instructions=instructions.content,
                    tools=tools,
                    tool_resources=tool_resources
                )
            )

            return await thread.send(f"Created assistant `{created.id}` ")

        except Exception as e:
            logger.exception(e)
            await int.response.send_message(f"Failed to start chat {str(e)}", ephemeral=True)

    @app_commands.command(name="update")
    @app_commands.guilds(ADMIN_SERVER_ID)
    async def update(self, int: discord.Interaction, assistant_id: str):
        """Update an assistant"""
        try:
            # only support updating assistant in text channel
            if isinstance(int.channel, discord.TextChannel):
                thread = None
            elif isinstance(int.channel, discord.Thread) and int.channel.name.startswith(ACTIVATE_BUILD_THREAD_PREFIX):
                thread = int.channel
            else:
                return

            # block servers not in allow list
            if should_block(guild=int.guild):
                return

            user = int.user
            logger.info(f"Update command by {user}")

            # Create embed
            embed = discord.Embed(
                description=f"<@{user.id}> wants to update an assistant! 🤖💬",
                color=discord.Color.blue(),
            )
            await int.response.send_message(embed=embed)

            # The current assistant
            assistant = await get_assistant(assistant_id)

            # create the thread
            if thread is None:
                response = await int.original_response()
                thread = await response.create_thread(
                    name=f"{ACTIVATE_BUILD_THREAD_PREFIX} - {assistant.name} - {user.name[:20]}",
                    slowmode_delay=1,
                    reason="gpt-bot",
                    auto_archive_duration=60,
                )

            # Description
            await thread.send("What is the new description of your assistant?")
            description = await self.bot.wait_for("message", check=lambda m: m.author == user)
            if description.content != ".":
                assistant.description = description.content

            # Instructions
            await thread.send("What are the new instructions for your assistant?")
            instructions = await self.bot.wait_for("message", check=lambda m: m.author == user)
            if instructions.content != ".":
                assistant.instructions = instructions.content

            # Tools
            await thread.send("What are the tools that your assistant can use?")
            
            tools = []

            # File retrieval
            retrieval_view = TrueFalseView()
            await thread.send("# Files Search", view=retrieval_view)
            retrieval_value = False
            try:
                retrieval_value = await asyncio.wait_for(retrieval_view.value, timeout=180)
                if retrieval_value:
                    tools.append({"type": "file_search"})
            except asyncio.TimeoutError:
                await thread.send("Timed out waiting for button click. Files was disabled.")

            # Code interpreter
            code_interpreter_view = TrueFalseView()
            await thread.send(
                "# Code Interpreter", 
                view=code_interpreter_view
            )
            code_interpreter_value = False
            try:
                code_interpreter_value = await asyncio.wait_for(code_interpreter_view.value, timeout=180)
                if code_interpreter_value:
                    tools.append({"type": "code_interpreter"})
            except asyncio.TimeoutError:
                await thread.send("Timed out waiting for button click. Code interpreter was disabled.")
            
            # Function Calling
            function_calling_view = TrueFalseView()
            await thread.send("# Function Calling", view=function_calling_view)
            function_calling_value = False
            try:
                function_calling_value = await asyncio.wait_for(function_calling_view.value, timeout=180)
            except asyncio.TimeoutError:
                await thread.send("Timed out waiting for button click")

            if function_calling_value:
                view = FunctionSelectView(thread=thread)
                available_functions = get_available_functions()

                for func in available_functions:
                    view.selectMenu.add_option(
                        label=func["function"]["name"],
                        value=func["function"]["name"],
                        description=func["function"]["description"][0:min([100, len(func["function"]["description"])])],
                    )

                await thread.send("Select the function:", view=view)

                try:
                    await asyncio.wait_for(view.wait(), timeout=180)
                    if view.selected_function:
                        func = next((f for f in available_functions if f["function"]["name"] == view.selected_function), None)
                        if func:
                            function_tool_dict = function_tool_to_dict(func)
                            tools.append(function_tool_dict)
                            await thread.send("Function was added to the assistant.")
                    else:
                        await thread.send("No function was added to the assistant.")
                except asyncio.TimeoutError:
                    await thread.send("Timed out waiting for function selection. No function was added to the assistant.")

            assistant.tools = tools # Update tools
            
            # Add file_ids to the assistant only if file retrieval or code interpreter is enabled
            if retrieval_value or code_interpreter_value:
                # Check if the user wants to keep the existing files
                keep_files_view = YesNoView(
                    {
                        "yes": "The existing files were removed.",
                        "no": "The existing files were not removed."
                    }
                )
                await thread.send(
                    "Would you like to **Keep** the files? If no, the existing files will be removed.", 
                    view=keep_files_view
                )
                
                keep_files_value = False
                try:
                    keep_files_value = await asyncio.wait_for(keep_files_view.value, timeout=180)
                except asyncio.TimeoutError:
                    await thread.send("Timed out waiting for button click. The existing files were not removed.")
                
                if keep_files_value:
                    tool_resources = assistant.tool_resources
                else:
                    tool_resources = dict(
                        file_search=None,
                        code_interpreter=None
                    )
                
                # Ask the user if they want to add more files
                file_upload_view = YesNoView(
                    {
                        "yes":"Please upload the files to be added to the assistant and send them at once if you want to add multiple files.",
                        "no": "No files will be added to the assistant."
                    }
                )

                await thread.send(
                    "Would you like to add files to the assistant?",
                    view=file_upload_view
                )
                
                file_upload_value = False
                try:
                    file_upload_value = await asyncio.wait_for(file_upload_view.value, timeout=180)
                except asyncio.TimeoutError:
                    await thread.send("Timed out waiting for button click. No files will be added to the assistant.")
                
                # Upload the files if the user wants to
                if file_upload_value:
                    message = await self.bot.wait_for("message", check=lambda m: m.author == user)
                    if message.attachments:
                        for attachment in message.attachments:
                            pseudo_file = ( 
                                attachment.filename, 
                                await attachment.read(), 
                                attachment.content_type
                            )
                            if retrieval_value:
                                if tool_resources["file_search"] is None:
                                    tool_resources["file_search"] = dict(
                                        vector_store_ids=list()
                                    )
                                    tool_resources["file_search"]["vector_store_ids"].append(
                                        await create_vector_store(
                                            name=f"{assistant.name} - Vector Store"
                                        )
                                    )
                                else:
                                    vector_store_id = tool_resources["file_search"]["vector_store_ids"][-1]
                                    _ = await update_vector_store(vector_store_id, pseudo_file)
                                
                            if code_interpreter_value:
                                if tool_resources["code_interpreter"] is None:
                                    tool_resources["code_interpreter"] = dict(
                                        file_ids=list()
                                    )
                                file_id = await upload_file(file=pseudo_file)
                                tool_resources["code_interpreter"]["file_ids"].append(file_id)
            
                assistant.tool_resources = tool_resources # Update tool_resources
            else:
                # Remove all file_ids if file retrieval and code interpreter are disabled
                assistant.tool_resources = dict(
                    file_search=None,
                    code_interpreter=None
                )

            # Update the assistant
            updated = await update_assistant(assistant)

            return await thread.send(f"Updated assistant `{updated.id}` ")

        except Exception as e:
            logger.exception(e)
            await int.response.send_message(f"Failed to start chat {str(e)}", ephemeral=True)

    @app_commands.command(name="show")
    @app_commands.guilds(ADMIN_SERVER_ID)
    @is_me()
    async def show(self, int: discord.Interaction, assistant_id: str):
        """Show the specified assistant"""
        await int.response.defer()
        assistant = await get_assistant(assistant_id)
        s = f"```Name: {assistant.name}\n"
        s += f"Description: {assistant.description}\n"
        s += f"Instructions: {assistant.instructions}\n"
        s += f"Tools: {assistant.tools}\n"
        s += f"ToolResources: {assistant.tool_resources}```"
        responses = split_into_shorter_messages(s)
        for response in responses:
            if len(response) > 0:
                await int.followup.send(content=response)

    @app_commands.command(name="list")
    @app_commands.guilds(ADMIN_SERVER_ID)
    async def list(self, int: discord.Interaction, offset: int = 0,
            max: int = MAX_ASSISTANT_LIST, search: str = ''):
        """List available assistants with optional limit (default MAX_ASSISTANT_LIST)"""
        await int.response.defer()
        assistants = await search_assistants(search=search, limit=offset+max)
        assistants = assistants[offset:]
        s = "Available Assistants 🤖 `[assistant_id] name - description`\n"
        for assistant in assistants:
            s1 = f"```{assistant.render()}```"
            if len(s + s1) > MAX_CHARS_PER_REPLY_MSG:
                await int.followup.send(content=s)
                s = ''
            s = s + s1
        await int.followup.send(content=s)

    @app_commands.command(name="delete")
    @app_commands.guilds(ADMIN_SERVER_ID)
    async def delete(self, int: discord.Interaction, assistant_id: str):
        """Delete the specified assistant"""
        await int.response.defer()  # defer the response to avoid timeout during openai_api call
        try:
            # only support deleting assistant in text channel
            if not isinstance(int.channel, discord.TextChannel):
                return

            # block servers not in allow list
            if should_block(guild=int.guild):
                return

            assistant = await get_assistant(assistant_id)

            embed = discord.Embed(
                title=f"Assistant {assistant.name}",
                description=f"Description: {assistant.description}",
                color=discord.Color.red(),
            )
            view = DeleteConfirmView(assistant=assistant)
            await int.followup.send(
                content=f"Are you sure you want to delete assistant `{assistant.id}`?",
                embed=embed,
                view=view,
            )

            user = int.user
            # TODO: check if the user has the permission to delete

            logger.info(f"Delete command by {user}")

        except Exception as e:
            if isinstance(e, openai.NotFoundError):
                if e.status_code == 404:
                    await int.followup.send(
                        f"Failed to delete assistant. No assistant found with id `{assistant_id}`."
                    )
            else:
                logger.exception(e)
                await int.followup.send(f"Failed to delete assistant. {str(e)}")


class DeleteConfirmView(discord.ui.View):
    def __init__(self, assistant: Assistant):
        super().__init__()
        self.assistant = assistant

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.red)
    async def delete(self, int: discord.Interaction, button: discord.ui.Button):
        await delete_assistant(self.assistant.id)
        await int.response.send_message(
            f"Deleted assistant {self.assistant.name} by {int.user.mention}"
        )
        self.stop()
        # disable the buttons
        for item in self.children:
            item.disabled = True
        await int.followup.edit_message(message_id=int.message.id, view=self)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def cancel(self, int: discord.Interaction, button: discord.ui.Button):
        await int.response.send_message("Cancelled deleting assistant", ephemeral=True)
        self.stop()
        # delete the original message
        await int.followup.delete_message(int.message.id)


class TrueFalseView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.value = asyncio.Future()
    @discord.ui.button(label="Enable", style=discord.ButtonStyle.green)
    async def true(self, int: discord.Interaction, button: discord.ui.Button):
        await int.response.send_message("Enabled", ephemeral=True)
        self.stop()
        # disable the buttons
        for item in self.children:
            item.disabled = True
        self.value.set_result(True)

    @discord.ui.button(label="Disable", style=discord.ButtonStyle.red)
    async def false(self, int: discord.Interaction, button: discord.ui.Button):
        await int.response.send_message("Disabled", ephemeral=True)
        self.stop()
        # disable the buttons
        for item in self.children:
            item.disabled = True
        self.value.set_result(False)

class YesNoView(discord.ui.View):
    def __init__(self, messages):
        super().__init__()
        self.value = asyncio.Future()
        self.messages = messages
    """
    A view with two buttons, "Yes" and "No".
    self.messages = {"yes": "Yes message", "no": "No message"}
    """
    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def true(self, int: discord.Interaction, button: discord.ui.Button):
        await int.response.send_message(self.messages["yes"], ephemeral=True)
        self.stop()
        # disable the buttons
        for item in self.children:
            item.disabled = True
        self.value.set_result(True)
    
    @discord.ui.button(label="No", style=discord.ButtonStyle.red)
    async def false(self, int: discord.Interaction, button: discord.ui.Button):
        await int.response.send_message(self.messages["no"], ephemeral=True)
        self.stop()
        # disable the buttons
        for item in self.children:
            item.disabled = True
        self.value.set_result(False)

async def setup(bot):
    await bot.add_cog(Assistant(bot))
