from typing import Dict

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "vi": {
        # Lỗi chung & cấu hình ban đầu
        "error_no_api_key": "[bold red]Lỗi: Vui lòng thiết lập GOOGLE_API_KEY trong file .env[/bold red]",
        "error_need_prompt_or_action": "[bold red]Lỗi: Cần cung cấp prompt hoặc một hành động cụ thể.[/bold red]",

        # Thông tin về history cơ bản
        "no_history_to_summarize": "[yellow]Không có lịch sử để tóm tắt. Hãy dùng --load hoặc --topic.[/yellow]",
        "history_dir_missing": "[yellow]Thư mục '{dir}' không tồn tại. Chưa có lịch sử nào được lưu.[/yellow]",
        "no_history_files_found": "[yellow]Không tìm thấy file lịch sử nào.[/yellow]",
        "history_browser_exit": "[yellow]Đã thoát trình duyệt lịch sử.[/yellow]",

        # __main__.py & history_handler.py
        "api_keys_loaded": "[dim]\U0001f511 Đã tải {count} API key(s)[/dim]",
        "agent_requires_prompt": "[bold red]Lỗi: Chế độ Agent yêu cầu một mục tiêu (prompt).[/bold red]",
        "history_action_prompt": "Bạn muốn [c]hat tiếp, [s]ummarize (tóm tắt), hay [q]uit? ",
        "action_quit": "[yellow]Đã thoát.[/yellow]",
        "history_loaded_from_file": "[green]Đã tải lịch sử từ '{path}'.[/green]",
        "memory_found_relevant": "[dim]\U0001f9e0 Đã tìm thấy trí nhớ liên quan...[/dim]",
        "reading_directory_context": "[yellow]Đang đọc ngữ cảnh thư mục...[/yellow]",
        "error_image_not_found": "[bold red]Lỗi: Không tìm thấy file ảnh '{path}'[/bold red]",
        "error_opening_image": "[bold red]Lỗi khi mở ảnh '{path}': {error}[/bold red]",
        "images_loaded_count": "[green]Đã tải lên {count} ảnh.[/green]",
        "file_saved_to": "\n[bold green]\u2705 Đã lưu kết quả vào file: [cyan]{path}[/cyan][/bold green]",
        "interrupted_by_user": "\n[yellow]Đã dừng bởi người dùng.[/yellow]",
        "unexpected_startup_error": "[bold red]Đã xảy ra lỗi khởi động không mong muốn: {error}[/bold red]",

        # History browser & hiển thị lịch sử
        "history_scanning_files": "[bold green]Đang quét các file lịch sử trong `{dir}/`...[/bold green]",
        "history_section_header": "\n--- [bold yellow]LỊCH SỬ TR\u00d2 CHUY\u1ec6N[/bold yellow] ---",
        "history_section_footer": "\n--- [bold yellow]K\u1ebeT TH\u00dac L\u1ecaCH S\u1eed[/bold yellow] ---\n",
        "history_user_label": "[bold cyan]You:[/bold cyan]",
        "history_ai_label": "[bold magenta]AI:[/bold magenta]",
        "history_table_title": "\U0001f4da Lịch sử Tr\u00f2 chuyện",
        "history_table_column_index": "#",
        "history_table_column_title": "Chủ \u0110ề Tr\u00f2 Chuyện",
        "history_table_column_last_updated": "Lần Cập Nhật Cuối",
        "history_select_prompt": "Nhập số để tiếp tục cuộc trò chuyện (nhấn Enter để thoát): ",
        "history_loading_selected": "\n[green]Đang tải lại cuộc trò chuyện: '{title}'...[/green]",
        "history_invalid_choice": "[yellow]Lựa chọn không hợp lệ.[/yellow]",
        "history_summary_start": "\n[bold yellow]Đang yêu cầu AI tóm tắt cuộc trò chuyện...[/bold yellow]",
        "history_summary_title": "\n[bold green]\U0001f4dd Tóm Tắt Cuộc Trò Chuyện:[/bold green] ",
        "error_history_summary": "[bold red]Lỗi khi tóm tắt lịch sử: {error}[/bold red]",

        # Chat mode
        "chat_mode_intro": "[bold green]Đã vào chế độ trò chuyện. Gõ 'exit' hoặc 'quit' để thoát.[/bold green]",
        "chat_cannot_save_history_incomplete": "\n[yellow]Không thể lưu lịch sử do phiên chat chưa hoàn tất.[/yellow]",
        "chat_no_new_content_to_save": "\n[yellow]Không có nội dung mới để lưu.[/yellow]",
        "chat_save_name_prompt": "\n[bold yellow]Lưu cuộc trò chuyện với tên (bỏ trống để AI tự đặt tên): [/bold yellow]",
        "chat_ai_thinking_title": "[cyan]AI đang nghĩ tên cho cuộc trò chuyện...[/cyan]",
        "chat_no_save_conversation": "\n[yellow]Không lưu cuộc trò chuyện.[/yellow]",
        "chat_history_saved_to": "\n[bold yellow]Lịch sử trò chuyện đã được lưu vào '{path}'.[/bold yellow]",
        "chat_cannot_save_history_error": "\n[yellow]Không thể lưu lịch sử: {error}[/yellow]",
        "chat_generic_error": "[bold red]Lỗi: {error}[/bold red]",

        # Config handler
        "config_fetching_models": "[bold green]Đang lấy danh sách các model khả dụng...[/bold green]",
        "config_no_models_found": "[bold red]Không tìm thấy model nào khả dụng.[/bold red]",
        "config_error_fetching_models": "[bold red]Lỗi khi lấy danh sách model: {error}[/bold red]",
        "config_model_selection_title": "Chọn một model để làm mặc định",
        "config_select_model_prompt": "Nhập số thứ tự của model bạn muốn chọn: ",
        "config_default_model_set": "\n[bold green]\u2705 Đã đặt model mặc định là: [cyan]{model}[/cyan][/bold green]",
        "config_fallback_order_updated": "[yellow]Thứ tự model dự phòng đã được cập nhật.[/yellow]",
        "config_invalid_choice": "[bold red]Lựa chọn không hợp lệ, vui lòng thử lại.[/bold red]",
        "config_please_enter_number": "[bold red]Vui lòng nhập một con số.[/bold red]",
        "config_selection_cancelled": "\n[yellow]Đã hủy lựa chọn.[/yellow]",
        "config_instruction_added": "[bold green]\u2705 Đã thêm chỉ dẫn mới:[/bold green] '{instruction}'",
        "config_instruction_exists": "[yellow]Chỉ dẫn đã tồn tại.[/yellow]",
        "config_no_instructions": "[yellow]Không có chỉ dẫn tùy chỉnh nào được lưu.[/yellow]",
        "config_instructions_table_title": "\U0001f4dd Các Chỉ Dẫn Tùy Chỉnh Đã Lưu",
        "config_invalid_instruction_index": "[bold red]Lỗi: Index không hợp lệ. Vui lòng chọn số từ 1 đến {max_index}.[/bold red]",
        "config_instruction_removed": "[bold green]\u2705 Đã xóa chỉ dẫn:[/bold green] '{instruction}'",
        "config_persona_saved": "[bold green]\u2705 Đã lưu persona [cyan]'{name}'[/cyan].[/bold green]",
        "config_no_personas": "[yellow]Không có persona nào được lưu.[/yellow]",
        "config_personas_table_title": "\U0001f47b Các Persona Đã Lưu",
        "config_persona_not_found": "[bold red]Lỗi: Không tìm thấy persona có tên '{name}'.[/bold red]",
        "config_persona_removed": "[bold green]\u2705 Đã xóa persona [cyan]'{name}'[/cyan].[/bold green]",

        # Utils.execute_suggested_commands
        "utils_ai_suggested_commands": "\n[bold yellow]AI đã đề xuất {count} lệnh thực thi:[/bold yellow]",
        "utils_execute_all_prompt": "Thực thi? [y]es/[n]o/[a]ll/[q]uit: ",
        "utils_skip_all_commands": "[yellow]Đã bỏ qua tất cả các lệnh.[/yellow]",
        "utils_execute_each_prompt": "Thực thi lệnh '[cyan]{command}[/cyan]'? [y/n/q]: ",
        "utils_stopped_execution": "[yellow]Đã dừng thực thi.[/yellow]",
        "utils_executing_command": "\n[italic green]\u25b6\ufe0f Đang thực thi '[cyan]{command}[/cyan]'...[/italic green]",
        "utils_execute_done": "[bold green]\u2705 Thực thi hoàn tất.[/bold green]",
        "utils_execute_error": "[bold red]Lỗi khi thực thi lệnh: {error}[/bold red]",
        "utils_command_skipped": "[yellow]Đã bỏ qua lệnh.[/yellow]",

        # Ghi file do AI đề xuất
        "write_file_confirmation": "[bold yellow]\u26a0\ufe0f AI muốn ghi vào file '{path}'. Nội dung sẽ được ghi đè nếu file tồn tại.[/bold yellow]",
        "write_file_success": "Đã ghi thành công vào file '{path}'.",
        "write_file_error": "Lỗi khi ghi file: {error}",
        "write_file_denied": "Người dùng đã từ chối hành động ghi file.",

        # Git & tiện ích code
        "git_no_changes_to_commit": "[yellow]Không có thay đổi nào trong repository để commit.[/yellow]",
        "git_auto_staging": "[yellow]Đang tự động stage tất cả các thay đổi (`git add .`)...[/yellow]",
        "git_no_staged_changes": "[yellow]Không có thay đổi nào được staged để commit sau khi chạy 'git add'.[/yellow]",
        "git_request_ai_commit_message": "\n[dim]\U0001f916 Đang yêu cầu AI viết commit message...[/dim]",
        "git_error_command": "[bold red]Lỗi khi chạy lệnh git: {error}[/bold red]",
        "git_unexpected_error": "[bold red]Đã xảy ra lỗi trong quá trình git-commit: {error}[/bold red]",
        "git_commit_message_full_suggested": "\n[green]AI đã đề xuất commit message sau:[/green]\n[yellow]{message}[/yellow]",
        "git_commit_message_short_suggested": "\n[green]AI đã đề xuất commit message ngắn:[/green]\n[yellow]{message}[/yellow]",
        "git_commit_message_empty": "[yellow]AI không trả về commit message hợp lệ.[/yellow]",

        "code_file_not_found": "[bold red]Lỗi: File '{path}' không tồn tại.[/bold red]",
        "code_running_tool": "[bold green]\U0001f916 Đang {tool_name} cho file [cyan]{path}[/cyan]...[/bold green]",
        "code_error_result": "[bold red]{message}[/bold red]",
        "code_result_title": "\n[bold green]\u2728 Kết quả {tool_name}:[/bold green]",
        "code_error_saving_file": "[bold red]Lỗi khi lưu file: {error}[/bold red]",

        # Agent handler
        "agent_project_name_default": "Không có tên",
        "agent_reasoning_default": "Không có giải thích.",
        "agent_header_project_name_label": "✨ Tên Dự Án: ",
        "agent_header_reasoning_label": "🧠 Lý do & Kiến trúc: ",
        "agent_structure_header": "\n📂 Cấu Trúc Thư Mục & File:",
        "agent_structure_tree_error": "[red]Không thể hiển thị cấu trúc thư mục.[/red]",
        "agent_plan_panel_title": "[bold green]📝 Kế Hoạch Dự Án Chi Tiết[/bold green]",

        "agent_master_panel_body": "[bold green]🤖 Agent Đa Năng Đã Kích Hoạt 🤖[/bold green]\n[yellow]Mục tiêu:[/yellow] {goal}",
        "agent_unexpected_analysis_error": "[bold red]Đã xảy ra lỗi không mong muốn trong pha phân tích: {error}[/bold red]",
        "agent_no_response_after_retries": "[bold red]Lỗi: Không thể lấy được phản hồi từ AI sau nhiều lần thử.[/bold red]",
        "agent_unknown_task_type": "[bold red]Lỗi: Agent trả về loại tác vụ không xác định: '{task_type}'[/bold red]",

        "agent_tool_action": "[yellow]🎬 Hành động:[/yellow] Gọi tool [bold cyan]{tool_name}[/bold cyan] với tham số {tool_args}",
        "agent_tool_status_running": "[green]Đang chạy tool {tool_name}...[/green]",

        "agent_empty_project_plan_error": "[bold red]Lỗi: Kế hoạch dự án trống.[/bold red]",
        "agent_execution_phase_start": "\n[bold green]🚀 Bắt đầu pha thực thi...[/bold green]",
        "agent_iteration_header": "\n[bold]--- Vòng {step}/{max_steps} ---[/bold]",
        "agent_executor_thought_title": "[bold magenta]Suy nghĩ của Executor[/bold magenta]",
        "agent_project_finished_default": "Dự án đã hoàn thành.",
        "agent_project_finished_title": "[bold green]✅ Dự Án Hoàn Thành[/bold green]",
        "agent_executor_result_title": "[bold blue]👀 Kết quả[/bold blue]",
        "agent_recreate_session_quota": "[green]... Tái tạo session với key mới...[/green]",
        "agent_executor_unrecoverable_error": "[bold red]Lỗi không thể phục hồi trong vòng lặp Executor: {error}[/bold red]",
        "agent_max_steps_reached": "[bold yellow]⚠️ Agent đã đạt đến giới hạn {max_steps} bước.[/bold yellow]",

        "agent_no_first_react_step": "[bold red]Lỗi: Không có bước ReAct đầu tiên.[/bold red]",
        "agent_simple_task_intro": "[green]=> Yêu cầu được phân loại là 'Tác vụ đơn giản', kích hoạt chế độ ReAct.[/green]",
        "agent_plan_title_panel": "[bold magenta]Kế Hoạch Của Agent[/bold magenta]",
        "agent_simple_task_finished_default": "Nhiệm vụ đã hoàn thành.",
        "agent_simple_task_finished_title": "[bold green]✅ Nhiệm Vụ Hoàn Thành[/bold green]",
        "agent_observation_title": "[bold blue]👀 Quan sát[/bold blue]",
        "agent_react_unrecoverable_error": "[bold red]Lỗi trong khi thực thi bước ReAct: {error}[/bold red]",
        "agent_dry_run_mode_header": "[bold yellow]⚠️ Agent đang chạy ở chế độ DRY-RUN: sẽ không thực thi tool, ghi file hay lệnh shell thật.[/bold yellow]",
        "agent_dry_run_tool_observation": "DRY-RUN: Lẽ ra sẽ gọi tool `{tool_name}` với tham số {tool_args}, nhưng hiện chỉ mô phỏng kết quả.",
        "agent_mode_label": "[dim]Chế độ: {mode}[/dim]",
        "agent_session_summary": "[bold green]✅ Agent đã hoàn thành sau {steps} bước (dry-run: {flag}).[/bold green]",
    },
    "en": {
        # General errors & bootstrap
        "error_no_api_key": "[bold red]Error: Please set GOOGLE_API_KEY in your .env file[/bold red]",
        "error_need_prompt_or_action": "[bold red]Error: You must provide a prompt or a specific action.[/bold red]",

        # Basic history messages
        "no_history_to_summarize": "[yellow]No history to summarize. Use --load or --topic.[/yellow]",
        "history_dir_missing": "[yellow]Directory '{dir}' does not exist. No history has been saved yet.[/yellow]",
        "no_history_files_found": "[yellow]No history files found.[/yellow]",
        "history_browser_exit": "[yellow]Exited history browser.[/yellow]",

        # __main__.py & history_handler.py
        "api_keys_loaded": "[dim]\U0001f511 Loaded {count} API key(s)[/dim]",
        "agent_requires_prompt": "[bold red]Error: Agent mode requires a goal (prompt).[/bold red]",
        "history_action_prompt": "Do you want to [c]hat, [s]ummarize, or [q]uit? ",
        "action_quit": "[yellow]Exited.[/yellow]",
        "history_loaded_from_file": "[green]Loaded history from '{path}'.[/green]",
        "memory_found_relevant": "[dim]\U0001f9e0 Found related memory...[/dim]",
        "reading_directory_context": "[yellow]Reading directory context...[/yellow]",
        "error_image_not_found": "[bold red]Error: Image file '{path}' not found[/bold red]",
        "error_opening_image": "[bold red]Error while opening image '{path}': {error}[/bold red]",
        "images_loaded_count": "[green]Loaded {count} image(s).[/green]",
        "file_saved_to": "\n[bold green]\u2705 Saved result to file: [cyan]{path}[/cyan][/bold green]",
        "interrupted_by_user": "\n[yellow]Interrupted by user.[/yellow]",
        "unexpected_startup_error": "[bold red]An unexpected startup error occurred: {error}[/bold red]",

        # History browser & view
        "history_scanning_files": "[bold green]Scanning history files in `{dir}/`...[/bold green]",
        "history_section_header": "\n--- [bold yellow]CHAT HISTORY[/bold yellow] ---",
        "history_section_footer": "\n--- [bold yellow]END OF HISTORY[/bold yellow] ---\n",
        "history_user_label": "[bold cyan]You:[/bold cyan]",
        "history_ai_label": "[bold magenta]AI:[/bold magenta]",
        "history_table_title": "\U0001f4da Chat History",
        "history_table_column_index": "#",
        "history_table_column_title": "Conversation Topic",
        "history_table_column_last_updated": "Last Updated",
        "history_select_prompt": "Enter a number to continue the conversation (press Enter to exit): ",
        "history_loading_selected": "\n[green]Loading conversation: '{title}'...[/green]",
        "history_invalid_choice": "[yellow]Invalid choice.[/yellow]",
        "history_summary_start": "\n[bold yellow]Requesting AI to summarize the conversation...[/bold yellow]",
        "history_summary_title": "\n[bold green]\U0001f4dd Conversation Summary:[/bold green] ",
        "error_history_summary": "[bold red]Error while summarizing history: {error}[/bold red]",

        # Chat mode
        "chat_mode_intro": "[bold green]Entered chat mode. Type 'exit' or 'quit' to leave.[/bold green]",
        "chat_cannot_save_history_incomplete": "\n[yellow]Cannot save history because the chat session is not complete.[/yellow]",
        "chat_no_new_content_to_save": "\n[yellow]No new content to save.[/yellow]",
        "chat_save_name_prompt": "\n[bold yellow]Save conversation as (leave empty to let AI name it): [/bold yellow]",
        "chat_ai_thinking_title": "[cyan]AI is thinking of a title for the conversation...[/cyan]",
        "chat_no_save_conversation": "\n[yellow]Conversation not saved.[/yellow]",
        "chat_history_saved_to": "\n[bold yellow]Chat history saved to '{path}'.[/bold yellow]",
        "chat_cannot_save_history_error": "\n[yellow]Could not save history: {error}[/yellow]",
        "chat_generic_error": "[bold red]Error: {error}[/bold red]",

        # Config handler
        "config_fetching_models": "[bold green]Fetching available models...[/bold green]",
        "config_no_models_found": "[bold red]No available models found.[/bold red]",
        "config_error_fetching_models": "[bold red]Error while fetching models: {error}[/bold red]",
        "config_model_selection_title": "Choose a default model",
        "config_select_model_prompt": "Enter the number of the model you want to select: ",
        "config_default_model_set": "\n[bold green]\u2705 Set default model to: [cyan]{model}[/cyan][/bold green]",
        "config_fallback_order_updated": "[yellow]Fallback model order has been updated.[/yellow]",
        "config_invalid_choice": "[bold red]Invalid choice, please try again.[/bold red]",
        "config_please_enter_number": "[bold red]Please enter a number.[/bold red]",
        "config_selection_cancelled": "\n[yellow]Selection cancelled.[/yellow]",
        "config_instruction_added": "[bold green]\u2705 Added new instruction:[/bold green] '{instruction}'",
        "config_instruction_exists": "[yellow]Instruction already exists.[/yellow]",
        "config_no_instructions": "[yellow]No custom instructions have been saved.[/yellow]",
        "config_instructions_table_title": "\U0001f4dd Saved Custom Instructions",
        "config_invalid_instruction_index": "[bold red]Error: Invalid index. Please choose a number between 1 and {max_index}.[/bold red]",
        "config_instruction_removed": "[bold green]\u2705 Removed instruction:[/bold green] '{instruction}'",
        "config_persona_saved": "[bold green]\u2705 Saved persona [cyan]'{name}'[/cyan].[/bold green]",
        "config_no_personas": "[yellow]No personas have been saved.[/yellow]",
        "config_personas_table_title": "\U0001f47b Saved Personas",
        "config_persona_not_found": "[bold red]Error: No persona found with name '{name}'.[/bold red]",
        "config_persona_removed": "[bold green]\u2705 Removed persona [cyan]'{name}'[/cyan].[/bold green]",

        # Utils.execute_suggested_commands
        "utils_ai_suggested_commands": "\n[bold yellow]AI suggested {count} command(s):[/bold yellow]",
        "utils_execute_all_prompt": "Execute? [y]es/[n]o/[a]ll/[q]uit: ",
        "utils_skip_all_commands": "[yellow]Skipped all commands.[/yellow]",
        "utils_execute_each_prompt": "Execute command '[cyan]{command}[/cyan]'? [y/n/q]: ",
        "utils_stopped_execution": "[yellow]Stopped execution.[/yellow]",
        "utils_executing_command": "\n[italic green]\u25b6\ufe0f Executing '[cyan]{command}[/cyan]'...[/italic green]",
        "utils_execute_done": "[bold green]\u2705 Execution finished.[/bold green]",
        "utils_execute_error": "[bold red]Error while executing command: {error}[/bold red]",
        "utils_command_skipped": "[yellow]Skipped command.[/yellow]",

        # File writes requested by AI
        "write_file_confirmation": "[bold yellow]\u26a0\ufe0f The AI wants to write to file '{path}'. The file will be overwritten if it exists.[/bold yellow]",
        "write_file_success": "Successfully wrote to file '{path}'.",
        "write_file_error": "Error while writing file: {error}",
        "write_file_denied": "User denied the write-file action.",

        # Git & code utilities
        "git_no_changes_to_commit": "[yellow]No changes in the repository to commit.[/yellow]",
        "git_auto_staging": "[yellow]Automatically staging all changes (`git add .`)...[/yellow]",
        "git_no_staged_changes": "[yellow]No staged changes to commit after running 'git add'.[/yellow]",
        "git_request_ai_commit_message": "\n[dim]\U0001f916 Requesting AI to write a commit message...[/dim]",
        "git_error_command": "[bold red]Error while running git command: {error}[/bold red]",
        "git_unexpected_error": "[bold red]An error occurred during git-commit: {error}[/bold red]",
        "git_commit_message_full_suggested": "\n[green]AI suggested the following commit message:[/green]\n[yellow]{message}[/yellow]",
        "git_commit_message_short_suggested": "\n[green]AI suggested a short commit message:[/green]\n[yellow]{message}[/yellow]",
        "git_commit_message_empty": "[yellow]AI did not return a valid commit message.[/yellow]",

        "code_file_not_found": "[bold red]Error: File '{path}' does not exist.[/bold red]",
        "code_running_tool": "[bold green]\U0001f916 Running {tool_name} for file [cyan]{path}[/cyan]...[/bold green]",
        "code_error_result": "[bold red]{message}[/bold red]",
        "code_result_title": "\n[bold green]\u2728 {tool_name} result:[/bold green]",
        "code_error_saving_file": "[bold red]Error while saving file: {error}[/bold red]",

        # Agent handler
        "agent_project_name_default": "No name",
        "agent_reasoning_default": "No reasoning provided.",
        "agent_header_project_name_label": "✨ Project Name: ",
        "agent_header_reasoning_label": "🧠 Reasoning & Architecture: ",
        "agent_structure_header": "\n📂 Directory & File Structure:",
        "agent_structure_tree_error": "[red]Unable to display directory structure.[/red]",
        "agent_plan_panel_title": "[bold green]📝 Detailed Project Plan[/bold green]",

        "agent_master_panel_body": "[bold green]🤖 Multi-Purpose Agent Activated 🤖[/bold green]\n[yellow]Goal:[/yellow] {goal}",
        "agent_unexpected_analysis_error": "[bold red]An unexpected error occurred during analysis phase: {error}[/bold red]",
        "agent_no_response_after_retries": "[bold red]Error: Could not get a response from the AI after multiple attempts.[/bold red]",
        "agent_unknown_task_type": "[bold red]Error: Agent returned an unknown task type: '{task_type}'[/bold red]",

        "agent_tool_action": "[yellow]🎬 Action:[/yellow] Calling tool [bold cyan]{tool_name}[/bold cyan] with args {tool_args}",
        "agent_tool_status_running": "[green]Running tool {tool_name}...[/green]",

        "agent_empty_project_plan_error": "[bold red]Error: Project plan is empty.[/bold red]",
        "agent_execution_phase_start": "\n[bold green]🚀 Starting execution phase...[/bold green]",
        "agent_iteration_header": "\n[bold]--- Iteration {step}/{max_steps} ---[/bold]",
        "agent_executor_thought_title": "[bold magenta]Executor Thoughts[/bold magenta]",
        "agent_project_finished_default": "The project has been completed.",
        "agent_project_finished_title": "[bold green]✅ Project Completed[/bold green]",
        "agent_executor_result_title": "[bold blue]👀 Result[/bold blue]",
        "agent_recreate_session_quota": "[green]... Recreating session with a new key...[/green]",
        "agent_executor_unrecoverable_error": "[bold red]Unrecoverable error in Executor loop: {error}[/bold red]",
        "agent_max_steps_reached": "[bold yellow]⚠️ Agent has reached the step limit of {max_steps}.[/bold yellow]",

        "agent_no_first_react_step": "[bold red]Error: No initial ReAct step provided.[/bold red]",
        "agent_simple_task_intro": "[green]=> The request was categorized as a 'Simple task', activating ReAct mode.[/green]",
        "agent_plan_title_panel": "[bold magenta]Agent Plan[/bold magenta]",
        "agent_simple_task_finished_default": "The task has been completed.",
        "agent_simple_task_finished_title": "[bold green]✅ Task Completed[/bold green]",
        "agent_observation_title": "[bold blue]👀 Observation[/bold blue]",
        "agent_react_unrecoverable_error": "[bold red]Unrecoverable error while executing ReAct step: {error}[/bold red]",
        "agent_dry_run_mode_header": "[bold yellow]⚠️ Agent is running in DRY-RUN mode: no tools, file writes, or shell commands will actually be executed.[/bold yellow]",
        "agent_dry_run_tool_observation": "DRY-RUN: Would call tool `{tool_name}` with args {tool_args}, but only simulating the result.",
        "agent_mode_label": "[dim]Mode: {mode}[/dim]",
        "agent_session_summary": "[bold green]✅ Agent finished after {steps} step(s) (dry-run: {flag}).[/bold green]",
    },
}


def tr(language: str, key: str, **kwargs) -> str:
    """Dịch key theo ngôn ngữ, fallback sang tiếng Việt nếu thiếu.

    language: mã ngôn ngữ, ví dụ "vi" hoặc "en".
    key: khóa thông điệp.
    kwargs: tham số format chuỗi (ví dụ {dir}).
    """
    lang = language if language in TRANSLATIONS else "vi"
    template = TRANSLATIONS.get(lang, {}).get(key) or TRANSLATIONS["vi"].get(key) or key
    try:
        return template.format(**kwargs)
    except Exception:
        # Nếu format lỗi (thiếu kwargs), trả nguyên template để không làm vỡ flow.
        return template
