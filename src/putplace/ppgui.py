"""PutPlace GUI Client using Kivy.

This module provides a graphical user interface for the PutPlace client,
allowing users to select directories, configure settings, and upload file
metadata to a PutPlace server.

Installation:
    pip install putplace[gui]

Usage:
    ppgui
"""

import os
import sys
import socket
import threading
from pathlib import Path
from typing import List, Optional

# Check if Kivy is available
try:
    from kivy.app import App
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.gridlayout import GridLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.textinput import TextInput
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.progressbar import ProgressBar
    from kivy.uix.filechooser import FileChooserListView
    from kivy.uix.popup import Popup
    from kivy.clock import Clock, mainthread
    from kivy.core.window import Window
except ImportError:
    print("Error: Kivy is not installed.")
    print("Please install with: pip install putplace[gui]")
    sys.exit(1)

# Import ppclient functions
try:
    from .ppclient import (
        calculate_sha256,
        get_file_stats,
        matches_exclude_pattern,
        get_hostname,
        get_ip_address,
    )
except ImportError:
    # Fallback for direct execution
    from ppclient import (
        calculate_sha256,
        get_file_stats,
        matches_exclude_pattern,
        get_hostname,
        get_ip_address,
    )

import httpx


class PutPlaceGUI(BoxLayout):
    """Main GUI layout for PutPlace client."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = 15
        self.spacing = 15

        # State variables
        self.selected_path: Optional[str] = None
        self.exclude_patterns: List[str] = []
        self.is_uploading = False
        self.upload_thread: Optional[threading.Thread] = None

        # Set window size and colors
        Window.size = (1000, 750)
        Window.clearcolor = (0.95, 0.95, 0.95, 1)  # Light gray background

        # Build UI
        self.build_header()
        self.build_file_selector()
        self.build_settings()
        self.build_exclude_patterns()
        self.build_progress_section()
        self.build_log_section()
        self.build_controls()

        # Auto-detect hostname and IP
        self.hostname_input.text = get_hostname()
        self.ip_input.text = get_ip_address()

    def build_header(self):
        """Build header section."""
        header = Label(
            text='PutPlace GUI Client',
            size_hint_y=None,
            height=60,
            font_size='28sp',
            bold=True,
            color=(0.2, 0.4, 0.7, 1)  # Blue text
        )
        self.add_widget(header)

    def build_file_selector(self):
        """Build file/directory selector section."""
        selector_layout = BoxLayout(orientation='vertical', size_hint_y=0.3, spacing=8)

        # Label
        selector_label = Label(
            text='Select Directory to Scan:',
            size_hint_y=None,
            height=35,
            font_size='18sp',
            bold=True,
            color=(0.2, 0.2, 0.2, 1),
            halign='left'
        )
        selector_label.bind(size=selector_label.setter('text_size'))
        selector_layout.add_widget(selector_label)

        # File chooser
        self.file_chooser = FileChooserListView(
            path=str(Path.home()),
            dirselect=True,
            size_hint_y=1
        )
        self.file_chooser.bind(on_submit=self.on_path_selected)
        selector_layout.add_widget(self.file_chooser)

        # Selected path display
        self.path_label = Label(
            text='No path selected',
            size_hint_y=None,
            height=35,
            font_size='15sp',
            color=(0.6, 0.6, 0.6, 1),
            italic=True
        )
        selector_layout.add_widget(self.path_label)

        self.add_widget(selector_layout)

    def build_settings(self):
        """Build settings section."""
        settings_layout = GridLayout(cols=2, size_hint_y=None, height=140, spacing=10)

        # Server URL
        settings_layout.add_widget(Label(
            text='Server URL:',
            size_hint_x=0.25,
            color=(0.2, 0.2, 0.2, 1),
            halign='right',
            valign='middle'
        ))
        self.server_input = TextInput(
            text='http://localhost:8000',
            multiline=False,
            size_hint_x=0.75,
            background_color=(1, 1, 1, 1),
            foreground_color=(0.2, 0.2, 0.2, 1),
            padding=[10, 8]
        )
        settings_layout.add_widget(self.server_input)

        # API Key
        settings_layout.add_widget(Label(
            text='API Key:',
            size_hint_x=0.25,
            color=(0.2, 0.2, 0.2, 1),
            halign='right',
            valign='middle'
        ))
        self.api_key_input = TextInput(
            text='',
            multiline=False,
            password=True,
            size_hint_x=0.75,
            background_color=(1, 1, 1, 1),
            foreground_color=(0.2, 0.2, 0.2, 1),
            padding=[10, 8]
        )
        settings_layout.add_widget(self.api_key_input)

        # Hostname
        settings_layout.add_widget(Label(
            text='Hostname:',
            size_hint_x=0.25,
            color=(0.2, 0.2, 0.2, 1),
            halign='right',
            valign='middle'
        ))
        self.hostname_input = TextInput(
            text='',
            multiline=False,
            size_hint_x=0.75,
            background_color=(1, 1, 1, 1),
            foreground_color=(0.2, 0.2, 0.2, 1),
            padding=[10, 8]
        )
        settings_layout.add_widget(self.hostname_input)

        # IP Address
        settings_layout.add_widget(Label(
            text='IP Address:',
            size_hint_x=0.25,
            color=(0.2, 0.2, 0.2, 1),
            halign='right',
            valign='middle'
        ))
        self.ip_input = TextInput(
            text='',
            multiline=False,
            size_hint_x=0.75,
            background_color=(1, 1, 1, 1),
            foreground_color=(0.2, 0.2, 0.2, 1),
            padding=[10, 8]
        )
        settings_layout.add_widget(self.ip_input)

        self.add_widget(settings_layout)

    def build_exclude_patterns(self):
        """Build exclude patterns section."""
        exclude_layout = BoxLayout(orientation='vertical', size_hint_y=None, height=130, spacing=8)

        # Header with add button
        header_layout = BoxLayout(size_hint_y=None, height=35, spacing=10)
        header_layout.add_widget(Label(
            text='Exclude Patterns:',
            font_size='18sp',
            bold=True,
            color=(0.2, 0.2, 0.2, 1),
            halign='left'
        ))
        add_btn = Button(
            text='Add',
            size_hint_x=None,
            width=80,
            background_color=(0.2, 0.6, 0.3, 1),
            color=(1, 1, 1, 1)
        )
        add_btn.bind(on_press=self.show_add_pattern_popup)
        header_layout.add_widget(add_btn)
        exclude_layout.add_widget(header_layout)

        # Patterns list
        scroll = ScrollView(size_hint_y=1)
        self.patterns_layout = BoxLayout(orientation='vertical', size_hint_y=None, spacing=5)
        self.patterns_layout.bind(minimum_height=self.patterns_layout.setter('height'))
        scroll.add_widget(self.patterns_layout)
        exclude_layout.add_widget(scroll)

        self.add_widget(exclude_layout)

    def build_progress_section(self):
        """Build progress display section."""
        progress_layout = BoxLayout(orientation='vertical', size_hint_y=None, height=70, spacing=8)

        self.progress_label = Label(
            text='Ready',
            size_hint_y=None,
            height=25,
            font_size='16sp',
            color=(0.2, 0.2, 0.2, 1),
            bold=True
        )
        progress_layout.add_widget(self.progress_label)

        self.progress_bar = ProgressBar(max=100, value=0, size_hint_y=None, height=25)
        progress_layout.add_widget(self.progress_bar)

        self.add_widget(progress_layout)

    def build_log_section(self):
        """Build log output section."""
        log_layout = BoxLayout(orientation='vertical', size_hint_y=0.3, spacing=8)

        log_label = Label(
            text='Log Output:',
            size_hint_y=None,
            height=35,
            font_size='18sp',
            bold=True,
            color=(0.2, 0.2, 0.2, 1),
            halign='left'
        )
        log_label.bind(size=log_label.setter('text_size'))
        log_layout.add_widget(log_label)

        scroll = ScrollView()
        self.log_output = TextInput(
            text='',
            readonly=True,
            multiline=True,
            size_hint_y=None,
            background_color=(1, 1, 1, 1),
            foreground_color=(0.2, 0.2, 0.2, 1),
            font_size='14sp'
        )
        self.log_output.bind(minimum_height=self.log_output.setter('height'))
        scroll.add_widget(self.log_output)
        log_layout.add_widget(scroll)

        self.add_widget(log_layout)

    def build_controls(self):
        """Build control buttons."""
        controls = BoxLayout(size_hint_y=None, height=55, spacing=12)

        self.start_btn = Button(
            text='Start Upload',
            background_color=(0.2, 0.5, 0.8, 1),
            color=(1, 1, 1, 1),
            font_size='16sp',
            bold=True
        )
        self.start_btn.bind(on_press=self.start_upload)
        controls.add_widget(self.start_btn)

        self.stop_btn = Button(
            text='Stop',
            disabled=True,
            background_color=(0.8, 0.3, 0.3, 1),
            color=(1, 1, 1, 1),
            font_size='16sp',
            bold=True
        )
        self.stop_btn.bind(on_press=self.stop_upload)
        controls.add_widget(self.stop_btn)

        clear_btn = Button(
            text='Clear Log',
            background_color=(0.6, 0.6, 0.6, 1),
            color=(1, 1, 1, 1),
            font_size='16sp'
        )
        clear_btn.bind(on_press=self.clear_log)
        controls.add_widget(clear_btn)

        self.add_widget(controls)

    # Event handlers

    def on_path_selected(self, instance, selection, touch):
        """Handle path selection."""
        if selection:
            self.selected_path = selection[0]
            self.path_label.text = f'Selected: {self.selected_path}'
            self.path_label.color = (0, 1, 0, 1)

    def show_add_pattern_popup(self, instance):
        """Show popup to add exclude pattern."""
        content = BoxLayout(orientation='vertical', spacing=10, padding=10)

        pattern_input = TextInput(
            multiline=False,
            hint_text='e.g., *.log, __pycache__, .git'
        )
        content.add_widget(pattern_input)

        buttons = BoxLayout(size_hint_y=None, height=40, spacing=10)

        add_btn = Button(text='Add')
        cancel_btn = Button(text='Cancel')

        buttons.add_widget(add_btn)
        buttons.add_widget(cancel_btn)
        content.add_widget(buttons)

        popup = Popup(
            title='Add Exclude Pattern',
            content=content,
            size_hint=(0.6, 0.3)
        )

        def add_pattern(btn):
            pattern = pattern_input.text.strip()
            if pattern:
                self.exclude_patterns.append(pattern)
                self.add_pattern_to_ui(pattern)
                self.log(f'Added exclude pattern: {pattern}')
            popup.dismiss()

        add_btn.bind(on_press=add_pattern)
        cancel_btn.bind(on_press=popup.dismiss)

        popup.open()

    def add_pattern_to_ui(self, pattern: str):
        """Add pattern to UI list."""
        pattern_layout = BoxLayout(size_hint_y=None, height=30, spacing=5)

        pattern_label = Label(text=pattern, size_hint_x=0.8)
        pattern_layout.add_widget(pattern_label)

        remove_btn = Button(text='Remove', size_hint_x=0.2)
        remove_btn.bind(on_press=lambda x: self.remove_pattern(pattern, pattern_layout))
        pattern_layout.add_widget(remove_btn)

        self.patterns_layout.add_widget(pattern_layout)

    def remove_pattern(self, pattern: str, widget):
        """Remove pattern from list."""
        if pattern in self.exclude_patterns:
            self.exclude_patterns.remove(pattern)
            self.patterns_layout.remove_widget(widget)
            self.log(f'Removed exclude pattern: {pattern}')

    @mainthread
    def log(self, message: str):
        """Add message to log output."""
        self.log_output.text += f'{message}\n'

    def clear_log(self, instance):
        """Clear log output."""
        self.log_output.text = ''

    def start_upload(self, instance):
        """Start upload process."""
        if self.is_uploading:
            self.log('Upload already in progress')
            return

        if not self.selected_path:
            self.log('Error: No directory selected')
            return

        if not self.api_key_input.text.strip():
            self.log('Error: API key is required')
            return

        # Disable start button, enable stop button
        self.start_btn.disabled = True
        self.stop_btn.disabled = False
        self.is_uploading = True

        # Start upload in background thread
        self.upload_thread = threading.Thread(target=self.upload_files, daemon=True)
        self.upload_thread.start()

    def stop_upload(self, instance):
        """Stop upload process."""
        self.is_uploading = False
        self.log('Stopping upload...')
        self.start_btn.disabled = False
        self.stop_btn.disabled = True

    def upload_files(self):
        """Upload files in background thread."""
        try:
            path = Path(self.selected_path)
            server_url = f"{self.server_input.text.rstrip('/')}/put_file"
            api_key = self.api_key_input.text.strip()
            hostname = self.hostname_input.text.strip()
            ip_address = self.ip_input.text.strip()

            self.log(f'Starting scan of: {path}')
            self.log(f'Server: {server_url}')

            # Collect files
            files_to_process = []
            if path.is_file():
                files_to_process.append(path)
            else:
                for file_path in path.rglob('*'):
                    if file_path.is_file():
                        # Check exclude patterns
                        relative_path = file_path.relative_to(path)
                        if matches_exclude_pattern(relative_path, self.exclude_patterns):
                            continue
                        files_to_process.append(file_path)

            total_files = len(files_to_process)
            self.log(f'Found {total_files} files to process')

            if total_files == 0:
                self.log('No files to upload')
                self.upload_complete()
                return

            # Process files
            processed = 0
            uploaded = 0
            errors = 0

            for file_path in files_to_process:
                if not self.is_uploading:
                    self.log('Upload cancelled by user')
                    break

                try:
                    # Calculate SHA256
                    sha256 = calculate_sha256(file_path)
                    stats = get_file_stats(file_path)

                    if not sha256 or not stats:
                        errors += 1
                        continue

                    # Prepare metadata
                    metadata = {
                        "filepath": str(file_path.absolute()),
                        "hostname": hostname,
                        "ip_address": ip_address,
                        "sha256": sha256,
                        "file_size": stats["file_size"],
                        "file_mode": stats["file_mode"],
                        "file_uid": stats["file_uid"],
                        "file_gid": stats["file_gid"],
                        "file_mtime": stats["file_mtime"],
                        "file_atime": stats["file_atime"],
                        "file_ctime": stats["file_ctime"],
                        "is_symlink": stats["is_symlink"],
                        "link_target": stats["link_target"],
                    }

                    # Send to server
                    headers = {"X-API-Key": api_key}
                    response = httpx.post(server_url, json=metadata, headers=headers, timeout=30.0)

                    if response.status_code == 201:
                        uploaded += 1
                        self.log(f'✓ Uploaded: {file_path.name}')
                    else:
                        errors += 1
                        self.log(f'✗ Error uploading {file_path.name}: {response.status_code}')

                except Exception as e:
                    errors += 1
                    self.log(f'✗ Error processing {file_path.name}: {str(e)}')

                processed += 1
                self.update_progress(processed, total_files)

            # Summary
            self.log('---')
            self.log(f'Upload complete: {uploaded} uploaded, {errors} errors, {processed} total')

        except Exception as e:
            self.log(f'Fatal error: {str(e)}')
        finally:
            self.upload_complete()

    @mainthread
    def update_progress(self, current: int, total: int):
        """Update progress bar and label."""
        percentage = (current / total) * 100 if total > 0 else 0
        self.progress_bar.value = percentage
        self.progress_label.text = f'Processing: {current}/{total} ({percentage:.1f}%)'

    @mainthread
    def upload_complete(self):
        """Reset UI after upload completes."""
        self.is_uploading = False
        self.start_btn.disabled = False
        self.stop_btn.disabled = True
        self.progress_label.text = 'Ready'
        self.progress_bar.value = 0


class PutPlaceApp(App):
    """Main Kivy application."""

    def build(self):
        """Build the application."""
        self.title = 'PutPlace GUI Client'
        return PutPlaceGUI()


def main():
    """Main entry point for GUI application."""
    try:
        PutPlaceApp().run()
    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)


if __name__ == '__main__':
    main()
