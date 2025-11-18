import os
import io
import time
import sys
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload

# ----------------------------------------------------------------------
# 1. SETUP INSTRUCTIONS (Reminder)
# ----------------------------------------------------------------------
# A. Install the necessary libraries:
#    pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
#
# B. Ensure 'credentials.json' is in the same directory and your Google
#    account is added as a 'Test User' in the Google Cloud Console.

SCOPES = ['https://www.googleapis.com/auth/drive']
TARGET_FOLDER_NAME = "CLI_Sorted_Archive"
DRIVE_ROOT_ID = 'root'

class DriveManager:
    """Manages all Google Drive API interactions."""

    def __init__(self):
        self.service = self._authenticate_and_get_service()
        self.user_info = None
        if self.service:
            self.user_info = self._get_user_info()

    def _authenticate_and_get_service(self):
        """Handles OAuth 2.0 authentication."""
        creds = None
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
                    creds = None
            
            if not creds:
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        'credentials.json', SCOPES)
                    creds = flow.run_local_server(port=0)
                except FileNotFoundError:
                    print("\nERROR: 'credentials.json' not found. Cannot proceed.")
                    return None
                except Exception as e:
                    print(f"\nAuthentication Error: {e}")
                    return None
            
            with open('token.json', 'w') as token:
                token.write(creds.to_json())

        try:
            service = build('drive', 'v3', credentials=creds)
            return service
        except Exception as e:
            print(f"Error building Drive service: {e}")
            return None

    def _get_user_info(self):
        """Fetches and returns the current user's email address."""
        if not self.service:
            return None
        try:
            # The 'about' resource provides information about the user's Drive.
            about = self.service.about().get(fields='user').execute()
            user_email = about.get('user', {}).get('emailAddress')
            return user_email
        except Exception as e:
            print(f"Error fetching user info: {e}")
            return "Unknown User"

    # --- Hierarchical Listing Functions ---

    def _fetch_all_files(self):
        """Fetches a large subset of files to build the tree structure."""
        if not self.service: return []
        
        # Max pageSize is 1000. For simplicity, we grab the first page.
        print("\n--- Fetching file list (up to 1000 items) ---")
        try:
            results = self.service.files().list(
                pageSize=1000,
                # Order folders first, then files by name
                orderBy="folder,name", 
                fields="nextPageToken, files(id, name, mimeType, parents)").execute()
            return results.get('files', [])
        except Exception as e:
            print(f"Error fetching files: {e}")
            return []

    def _build_tree(self, files):
        """Organizes a flat list of files into a hierarchical tree structure."""
        file_map = {file['id']: file for file in files}
        tree = {} # Dictionary to hold top-level files/folders

        for file in files:
            file['children'] = []
            file['is_folder'] = file['mimeType'] == 'application/vnd.google-apps.folder'
            
            parents = file.get('parents', [])
            
            # If the file is not attached to a parent that we also fetched, 
            # or if its parent is the Drive root, treat it as a top-level item.
            is_attached = False
            for parent_id in parents:
                # Attach to the first parent folder found in the map
                if parent_id in file_map and file_map[parent_id]['is_folder']:
                    file_map[parent_id]['children'].append(file)
                    is_attached = True
                    break 

            # If not attached to a fetched folder, add it to the top-level tree view
            if not is_attached:
                tree[file['id']] = file
                
        return tree

    def _print_tree(self, node, level=0):
        """Recursively prints the file/folder tree with indentation and details."""
        indent = "  | " * level
        
        # Determine the icon and format the display string
        icon = "📂" if node.get('is_folder') else "📄"
        type_str = "[Folder]" if node.get('is_folder') else "[File]"
        
        # Print the current node: Indent | Icon Type Name (ID)
        print(f"{indent}{icon} {type_str:<8} {node['name'][:40]:<40} (ID: {node['id']})")
        
        # Recursively print children, if any
        if node.get('is_folder') and node.get('children'):
            # Sort children to keep folders together and then by name
            sorted_children = sorted(node['children'], key=lambda x: (not x['is_folder'], x['name']))
            for child in sorted_children:
                self._print_tree(child, level + 1)
                
    def list_files(self):
        """Public method to display files in a tree structure."""
        files = self._fetch_all_files()
        if not files:
            print("No files found or error during fetch.")
            return

        print("\n--- Building and Displaying File Tree ---")
        tree_roots = self._build_tree(files)

        # Print all nodes treated as roots
        # Sort roots: folders first, then files, then by name
        sorted_roots = sorted(tree_roots.values(), key=lambda x: (not x['is_folder'], x['name']))
        
        if not sorted_roots:
            print("No top-level files or folders found.")
            return

        for file in sorted_roots:
            self._print_tree(file)

    # --- Utility Functions (Updated to use internal fetch) ---

    def upload_file(self, local_filepath, mime_type='application/octet-stream'):
        """Uploads a local file to the root of the user's Drive."""
        if not self.service: return

        if not os.path.exists(local_filepath):
            print(f"❌ Error: Local file not found at '{local_filepath}'.")
            print("Please create the file or use 'example_file.txt' for testing.")
            return

        file_metadata = {'name': os.path.basename(local_filepath)}
        media = MediaFileUpload(local_filepath, mimetype=mime_type)

        try:
            print(f"📤 Uploading '{os.path.basename(local_filepath)}'...")
            uploaded_file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name').execute()
            print(f"✅ Successfully uploaded! Name: {uploaded_file['name']} | ID: {uploaded_file['id']}")
        except Exception as e:
            print(f"❌ Error during upload: {e}")

    def delete_file(self, file_id):
        """Deletes a file by ID."""
        if not self.service: return
        try:
            print(f"🗑️ Deleting file with ID: {file_id}...")
            # Use delete() to move the file to trash.
            self.service.files().delete(fileId=file_id).execute()
            print(f"✅ Successfully deleted (moved to trash).")
        except Exception as e:
            print(f"❌ Error during deletion: {e}")
    
    def find_or_create_folder(self, folder_name):
        """Searches for a folder by name and creates it if not found."""
        if not self.service: return None
        q = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and 'root' in parents and trashed=false"
        results = self.service.files().list(q=q, fields="files(id)").execute()
        folders = results.get('files', [])
        
        if folders:
            return folders[0]['id']
        else:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            folder = self.service.files().create(body=file_metadata, fields='id').execute()
            return folder.get('id')

    def sort_demo(self):
        """Demonstrates the core sorting logic (moving a file to a designated folder)."""
        if not self.service: return

        print("\n--- Initiating Sorting Demo ---")
        # 1. Get files to find a candidate using the new fetch function
        all_files = self._fetch_all_files()
        
        file_to_move = None
        for item in all_files:
            # Pick the first non-folder file that has a parent
            if item['mimeType'] != 'application/vnd.google-apps.folder' and item.get('parents'):
                file_to_move = item
                break

        if not file_to_move:
            print("\n⚠️ No suitable file found to demonstrate sorting. Please upload a file first.")
            return
            
        FILE_ID_TO_MOVE = file_to_move['id']
        CURRENT_PARENT_ID = file_to_move['parents'][0]
        
        print(f"Selected file: '{file_to_move['name']}'")

        # 2. Find or Create the target folder.
        target_folder_id = self.find_or_create_folder(TARGET_FOLDER_NAME)
        
        if target_folder_id and CURRENT_PARENT_ID != target_folder_id:
             self._move_file(FILE_ID_TO_MOVE, CURRENT_PARENT_ID, target_folder_id)
        elif target_folder_id:
            print(f"ℹ️ File is already in the target folder ({TARGET_FOLDER_NAME}). Skipping move.")
            
    def _move_file(self, file_id, current_parent_id, new_parent_id):
        """Internal function to execute the move operation."""
        try:
            # Get current parents
            file = self.service.files().get(fileId=file_id, fields='parents, name').execute()
            previous_parents = ",".join(file.get('parents'))
            file_name = file.get('name')

            print(f"🔄 Moving '{file_name}' to folder ID: {new_parent_id}...")
            
            moved_file = self.service.files().update(
                fileId=file_id,
                addParents=new_parent_id,
                removeParents=previous_parents,
                fields='id, parents, name'
            ).execute()

            print(f"✅ Move successful! New Parent: {new_parent_id}")

        except Exception as e:
            print(f"❌ An error occurred while moving the file: {e}")

def main_menu():
    """Interactive CLI menu loop."""
    print("\n\n" + "="*50)
    print(" G D R I V E  -  O R G A N I Z E R  C L I ")
    print("="*50)

    manager = DriveManager()
    if not manager.service:
        print("Setup incomplete. Please check 'credentials.json' and your network connection.")
        return

    # Display logged-in user immediately
    manager.display_user_info()

    while True:
        print("\n" + "-"*30)
        print("Menu Options:")
        print("1. List Files (Hierarchical View)") # Updated text
        print("2. Upload a File")
        print("3. Delete a File (by ID)")
        print("4. Run Sorting Demo")
        print("5. Check Logged-in User")
        print("6. Exit")
        print("-" * 30)

        choice = input("Enter your choice (1-6): ").strip()
        
        if choice == '1':
            manager.list_files() # Calls the new hierarchical list

        elif choice == '2':
            # Use 'example_file.txt' as a default test path
            path = input("Enter local file path to upload (e.g., example_file.txt): ").strip()
            manager.upload_file(path)

        elif choice == '3':
            file_id = input("Enter the ID of the file to delete: ").strip()
            if file_id:
                manager.delete_file(file_id)

        elif choice == '4':
            manager.sort_demo()

        elif choice == '5':
            manager.display_user_info()

        elif choice == '6':
            print("Exiting GDrive Organizer. Goodbye!")
            sys.exit(0)

        else:
            print("Invalid choice. Please enter a number between 1 and 6.")
            
        input("\nPress ENTER to continue...") # Pause for readability

if __name__ == '__main__':
    # Add a buffer for robust error handling on first run
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\nExiting GDrive Organizer. Goodbye!")
        sys.exit(0)
    except NameError:
        print("\n!!! CRITICAL ERROR !!!")
        print("You must run the installation command first:")
        print("pip install google-api-python-client google-auth-oauthlib google-auth-httplib2")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        sys.exit(1)