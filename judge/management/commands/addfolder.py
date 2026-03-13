import csv
import secrets
import string
import re
import unicodedata
import os

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import connection
from django.apps import apps

from judge.models import Language, Profile, Organization

ALPHABET = string.ascii_letters + string.digits


def generate_password():
    return ''.join(secrets.choice(ALPHABET) for _ in range(8))


def add_user(username, fullname, email, password):

    user = User(username = username, email = email, first_name = fullname, is_active = True)
    user.set_password(password)
    user.save()

    profile = Profile(user = user)
    profile.language = Language.objects.get(key = settings.DEFAULT_USER_LANGUAGE)
    profile.save()

def add_org(username, organization):
    user = User.objects.get(username = username)
    profile = Profile.objects.get(user = user)
    organization = Organization.objects.get(short_name = organization) 
    if organization not in profile.organizations.all():
        profile.organizations.add(organization)
        print(f"Organization {organization.name} added to profile for user {username}.")
    else:
        print(f"Organization {organization.name} already exists in profile for user {username}.")

def simplify_string(input_string):
    accents_translation = str.maketrans(
        "àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ",
        "aaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyyd"
    )
    input_string = input_string.translate(accents_translation)
    simplified = re.sub(r'[^a-zA-Z0-9]', '', input_string.lower())
    return simplified
    
def normalize_string(input_str):
    normalized_str = ''.join(
        c for c in unicodedata.normalize('NFD', input_str)
        if unicodedata.category(c) != 'Mn'
    )
    words = normalized_str.split()
    first_letters = ''.join(word[0] for word in words if word)
    cleaned_str = re.sub(r'[^a-zA-Z0-9]', '', first_letters)
    digits = re.sub(r'[^0-9]', '', normalized_str)
    result = (cleaned_str + digits).lower()
    return result

def is_positive_integer(input_str):
    if input_str.isdigit() and int(input_str) > 0:
        return True
    return False
class Command(BaseCommand):
    help = 'batch create users'

    def add_arguments(self, parser):
        parser.add_argument('input', help='csv file containing username and fullname')
        parser.add_argument('output', help='where to store output csv file')

    def handle(self, *args, **options):

        folder_path = os.path.join(settings.BASE_DIR, options['input'])
        folder_path_out = os.path.join(settings.BASE_DIR, options['output'])
        for file_name in os.listdir(folder_path):
            if (file_name.find(".~") == -1):
                file_path = os.path.join(folder_path, file_name)
                if os.path.isfile(file_path):  
                    file_path_out = os.path.join(folder_path_out, file_name);
                    print(file_path)
                    print(file_path_out)

                    fin = open(file_path, 'r')
                    fout = open(file_path_out, 'w', newline='')

                    writer = csv.DictWriter(fout, fieldnames=['username', 'fullname', 'password'])
                    writer.writeheader()

                    csv_reader = csv.reader(fin)
                    data = [row for row in csv_reader]

                    row = 0
                    while (str(data[row][0]) != "admin"):
                        row += 1
                    username_admin = str(data[row][1])
                    row += 1
                    name_organization = str(data[row][0])
                    slug = normalize_string(name_organization)
                
                    if Organization.objects.filter(name = name_organization).exists():
                        print (name_organization + " already exists!")
                    else:
                        org = Organization(name = name_organization, slug = slug, short_name = slug, about = name_organization, is_open = 0, is_unlisted = 0)
                        
                        user_admin = User.objects.get(username = username_admin)
                        
                        profile_admin = Profile.objects.get(user = user_admin)
                        org.save()
                        org.admins.add(profile_admin)
                
                    while (str(data[row][0]) != "STT"):
                        row += 1
                    for row in range(row + 1, len(data)):
                        username = str(data[row][2])
                        fullname = str(data[row][3]) + " " + str(data[row][4])
                        email = str(data[row][7])
                        password = generate_password()

                        if User.objects.filter(username = username).exists():
                            print(username + " already exists!")
                            user = User.objects.get(username = username)
                            if (user.email == ""):
                                print(username + " add email " + email)
                                user.email = email
                                user.save()
                            # profile = Profile.objects.get(user = user) // ???

                        else:
                            add_user(username, fullname, email, password)
                            writer.writerow({
                                'username': username,
                                'fullname': fullname,
                                'password': password,
                            })
                        add_org(username, slug)
                    fin.close()
                    fout.close()
