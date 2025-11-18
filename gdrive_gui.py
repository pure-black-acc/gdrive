import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import sys
import os

# Assuming DriveManager is in gdrive_manager.py in the same directory
try:
    from gdrive_manager import DriveManager
except ImportError:
    print("Error: Could not import DriveManager. Make sure 'gdrive_manager.py' is in the same folder.")
    sys.exit(1)

# --- 1. Custom Console Redirection Class ---
# This class redirects all print() statements to the GUI's text widget.
class TextRedirector(object):
    """A helper class to redirect standard output (sys.stdout) to a Tkinter Text widget."""
    def __init__(self, widget, tag="stdout"):
        self.widget = widget
        self.tag = tag

    def write(self, str):
        self.widget.configure(state="normal")
        self.widget.insert(tk.END, str, (self.tag,))
        self.widget.see(tk.END) # Auto-scroll to the bottom
        self.widget.configure(state="disabled")

    def flush(self):
        # Tkinter Text widgets often require a flush to update immediately
        pass

# --- 2. Main GUI Application Class ---
class GDriveApp:
    def __init__(self, master):
        self.master = master
        master.title("Google Drive Organizer GUI")
        master.geometry("800x600")
        
        # Configure the grid layout
        master.grid_columnconfigure(0, weight=1)
        master.grid_columnconfigure(1, weight=1)
        master.grid_rowconfigure(2, weight=1) # The output area should expand

        self.drive_manager = None
        
        # UI components that need to be accessed by methods
        self.upload_path_var = tk.StringVar(value="Select a file to upload...")
        self.delete_id_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Initializing...")

        self._create_widgets()
        
        # Start the Drive Manager initialization in a separate thread
        self._run_in_thread(self._initialize_manager)
        
        # Redirect print statements to the output area
        sys.stdout = TextRedirector(self.output_text, "stdout")
        sys.stderr = TextRedirector(self.output_text, "stderr")

    def _create_widgets(self):
        """Builds all the main GUI components."""
        
        # --- Top Status Bar ---
        status_frame = ttk.Frame(self.master, padding="10")
        status_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
        status_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Label(status_frame, text="Status:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        ttk.Label(status_frame, textvariable=self.status_var, foreground="blue").grid(row=0, column=1, padx=5, pady=5, sticky="w")

        # --- Main Control Frame ---
        control_frame = ttk.LabelFrame(self.master, text="Drive Operations", padding="10")
        control_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=10, sticky="ew")
        control_frame.grid_columnconfigure(0, weight=1)
        control_frame.grid_columnconfigure(1, weight=1)
        control_frame.grid_columnconfigure(2, weight=1)
        
        # 1. List Files Button
        ttk.Button(control_frame, text="1. List Files (Tree View)", command=lambda: self._run_in_thread(self.list_files)).grid(row=0, column=0, padx=5, pady=5, sticky="ew")

        # 2. Upload File Controls
        ttk.Entry(control_frame, textvariable=self.upload_path_var, state='readonly').grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        ttk.Button(control_frame, text="Select File...", command=self.select_upload_file).grid(row=1, column=1, padx=5, pady=5, sticky="w")
        ttk.Button(control_frame, text="2. Upload File", command=lambda: self._run_in_thread(self.upload_file)).grid(row=1, column=2, padx=5, pady=5, sticky="ew")
        
        # 3. Delete File Controls
        ttk.Label(control_frame, text="File ID to Delete:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        ttk.Entry(control_frame, textvariable=self.delete_id_var).grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(control_frame, text="3. Delete File", command=lambda: self._run_in_thread(self.delete_file)).grid(row=2, column=2, padx=5, pady=5, sticky="ew")
        
        # 4. Sorting Demo Button
        ttk.Button(control_frame, text="4. Run Sorting Demo", command=lambda: self._run_in_thread(self.sort_demo)).grid(row=3, column=0, padx=5, pady=5, sticky="ew")
        
        # 5. User Info Button
        ttk.Button(control_frame, text="5. Check User", command=self.check_user).grid(row=3, column=1, padx=5, pady=5, sticky="ew")

        # 6. Exit Button
        # FIX: Changed 'master.quit' to 'self.master.quit' to reference the instance variable
        ttk.Button(control_frame, text="6. Exit", command=self.master.quit, style="Danger.TButton").grid(row=3, column=2, padx=5, pady=5, sticky="ew")
        
        # --- Output Area ---
        output_frame = ttk.LabelFrame(self.master, text="Console Output", padding="5")
        output_frame.grid(row=2, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")
        output_frame.grid_rowconfigure(0, weight=1)
        output_frame.grid_columnconfigure(0, weight=1)
        
        self.output_text = tk.Text(output_frame, height=15, state="disabled", wrap="word", font=('Consolas', 10))
        self.output_text.grid(row=0, column=0, sticky="nsew")
        
        # Scrollbar for output area
        scrollbar = ttk.Scrollbar(output_frame, command=self.output_text.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.output_text['yscrollcommand'] = scrollbar.set
        
        # Custom style for the exit button
        style = ttk.Style()
        style.configure("Danger.TButton", foreground="white", background="red", font=('Arial', 10, 'bold'))

    # --- 3. Threading Helper ---
    def _run_in_thread(self, func, *args):
        """Starts a given function in a new thread to keep the GUI responsive."""
        thread = threading.Thread(target=func, args=args)
        thread.daemon = True # Allows the thread to exit with the main program
        thread.start()

    # --- 4. DriveManager Wrappers (Run in Thread) ---
    def _initialize_manager(self):
        """Initializes the DriveManager and updates status."""
        self.status_var.set("Connecting to Google Drive API...")
        self.master.config(cursor="wait")
        
        # Initialize the manager (this handles auth)
        manager = DriveManager()
        
        if manager.service:
            self.drive_manager = manager
            self.status_var.set(f"Connected: {manager.user_info}")
            messagebox.showinfo("Success", f"Successfully connected to Drive as: {manager.user_info}")
        else:
            self.status_var.set("Authentication Failed. Check credentials.json.")
            messagebox.showerror("Error", "Authentication failed. See console output for details.")
            
        self.master.config(cursor="") # Reset cursor

    def list_files(self):
        """Calls list_files on the manager and prints output via redirection."""
        if not self.drive_manager: 
            messagebox.showwarning("Warning", "Manager not initialized.")
            return

        self.status_var.set("Fetching files...")
        self.master.config(cursor="wait")
        
        # Clear previous output
        self.output_text.configure(state="normal")
        self.output_text.delete(1.0, tk.END)
        self.output_text.configure(state="disabled")

        # The manager's list_files uses print(), which is redirected.
        self.drive_manager.list_files()
        
        self.status_var.set("Ready.")
        self.master.config(cursor="")

    def select_upload_file(self):
        """Opens a file dialog to select the file path."""
        filepath = filedialog.askopenfilename(
            title="Select File to Upload",
            filetypes=[("All files", "*.*")]
        )
        if filepath:
            self.upload_path_var.set(filepath)

    def upload_file(self):
        """Uploads the selected file."""
        if not self.drive_manager: 
            messagebox.showwarning("Warning", "Manager not initialized.")
            return
            
        filepath = self.upload_path_var.get()
        if not os.path.exists(filepath):
            messagebox.showerror("Error", "File path invalid or file not found.")
            return

        self.status_var.set(f"Uploading {os.path.basename(filepath)}...")
        self.master.config(cursor="wait")
        
        self.drive_manager.upload_file(filepath)
        
        self.status_var.set("Ready.")
        self.master.config(cursor="")

    def delete_file(self):
        """Deletes the file by ID."""
        if not self.drive_manager: 
            messagebox.showwarning("Warning", "Manager not initialized.")
            return
            
        file_id = self.delete_id_var.get().strip()
        if not file_id:
            messagebox.showerror("Error", "Please enter a valid File ID.")
            return
            
        if not messagebox.askyesno("Confirm Deletion", f"Are you sure you want to delete file ID: {file_id}?"):
            return

        self.status_var.set(f"Deleting file {file_id}...")
        self.master.config(cursor="wait")
        
        self.drive_manager.delete_file(file_id)
        
        self.status_var.set("Ready.")
        self.master.config(cursor="")
        self.delete_id_var.set("") # Clear input field

    def sort_demo(self):
        """Runs the sorting demo."""
        if not self.drive_manager: 
            messagebox.showwarning("Warning", "Manager not initialized.")
            return
            
        self.status_var.set("Running sorting demo...")
        self.master.config(cursor="wait")
        
        self.drive_manager.sort_demo()
        
        self.status_var.set("Ready.")
        self.master.config(cursor="")

    def check_user(self):
        """Checks and displays the logged-in user info."""
        if not self.drive_manager: 
            self.status_var.set("Manager not initialized. Try reconnecting.")
            return
            
        # The display_user_info method uses print(), which is redirected.
        self.drive_manager.display_user_info()

if __name__ == '__main__':
    root = tk.Tk()
    app = GDriveApp(root)
    root.mainloop()