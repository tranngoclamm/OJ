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
    alphabet = ALPHABET.replace('l', '')
    return ''.join(secrets.choice(alphabet) for _ in range(8))


def add_user(username, fullname, password):

    user = User(username = username, first_name = fullname, is_active = True)
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
                    username_admin = "dungpt"

                    row = 4
                    # while (str(data[row][0]) != "admin"):
                    #     row += 1
                    
                    # while (str(data[row][0]) != "name"):
                    #     row += 1
                    ten_mon = str(data[row][0]).split(":")[1].strip()
                    print(ten_mon)
                    row = 6
                    s_mot = str(data[row][0])
                    parts = [p.strip() for p in s_mot.split("  ") if ":" in p]
                    data_mot = {}
                    for p in parts:
                        key, value = p.split(":", 1)
                        data_mot[key.strip()] = value.strip()

                    ngay_thi = data_mot.get("Ngày thi").strip()
                    ca_thi = data_mot.get("Ca thi").strip()
                    phong_thi = data_mot.get("Phòng thi").strip()
                    print(ngay_thi)
                    print(ca_thi)
                    print(phong_thi)

                    name_organization = "TKTPH " + ten_mon + " " + ngay_thi + " " + ca_thi

                    slug = normalize_string(name_organization)
                
                    if Organization.objects.filter(name = name_organization).exists():
                        print (name_organization + " already exists!")
                    else:
                        org = Organization(name = name_organization, slug = slug, short_name = slug, about = name_organization, is_open = 0, is_unlisted = 1, is_official = 1)
                        
                        user_admin = User.objects.get(username = username_admin)
                        
                        profile_admin = Profile.objects.get(user = user_admin)
                        org.save()
                        org.admins.add(profile_admin)
                
                    while (str(data[row][0]) != "TT"):
                        row += 1
                    row += 2
                    while (str(data[row][0]).isdigit() == True):
                        username = "THI_" + str(data[row][2])
                        fullname = str(data[row][3]) + " " + str(data[row][4])
                        password = generate_password()
                        
                        if User.objects.filter(username = username).exists():
                            print(username + " already exists!")
                            user = User.objects.get(username = username)
                            user.set_password(password)
                            if (user.email != ""):
                                user.email = ""
                            user.save()
                            # profile = Profile.objects.get(user = user) // ???

                        else:
                            add_user(username, fullname, password)

                        add_org(username, slug)
                        writer.writerow({
                            'username': username,
                            'fullname': fullname,
                            'password': password,
                        })
                        row += 1
                        
                    for i in range(1, 3):
                        username = "THI_" + normalize_string(phong_thi) + "_" + str(i)
                        fullname = username
                        password = generate_password()
                        
                        if User.objects.filter(username = username).exists():
                            print(username + " already exists!")
                            user = User.objects.get(username = username)
                            user.set_password(password)
                            if (user.email != ""):
                                user.email = ""
                            user.save()
                            # profile = Profile.objects.get(user = user) // ???

                        else:
                            add_user(username, fullname, password)

                        add_org(username, slug)
                        writer.writerow({
                            'username': username,
                            'fullname': fullname,
                            'password': password,
                        })
                    fin.close()
                    fout.close()
