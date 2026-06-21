from pywikibot.config import register_families_folder

# Register the project-local family file(s) in ./families. The path is relative
# to the working directory, which (like templates/, output/, downloads/) is the
# project root when the importer or tests run.
register_families_folder("families")

family = "deckenmalerei"
mylang = "deckenmalerei"

usernames["deckenmalerei"]["deckenmalerei"] = "Admin"
password_file = "user-password.cfg"

# Be a well-behaved bot against the production wiki: throttle writes and respect
# server replication lag (pywikibot backs off automatically when maxlag is hit).
put_throttle = 0
maxlag = 1000
