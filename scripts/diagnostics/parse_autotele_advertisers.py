import re
import json

raw_text = """
@rahma4565
@Adsazza
@Mariam_Ads
@joee_ads
@maysa_ads
@adprofx Dina Ads
@AdsSafwat Safwat
@Emanads000
@rahma4565 rahma ads
@ADSSALMAa
@farida_ads
@Mohamed_ads97
@Asmaaa_ads
@Myaaaarrrr
@faridaads
@Mairaads
@lina_bnm
@mai_promoter
@abdo0o0o0oo
@MohammedAds33
@AesyGul
@Maha2210
@fatenexchange
@MaryamAds1
@EliteTradersAd
@Elsaidd22
@AdSwift
@Lamar_Ads
@MOKHTARR1
@HayamAd2j
@ADSSALMAa
@Jamilaads
@Sarah_Ads
@uniqads2
Meromero3131
@mayar_medhat1012
@nancy_ads1
@Abou_yaqoub
@EmaAds
@Stateuntied_ads
@Khaled_ads
@malak_ads22
@rahma4565
@Maya_ADS1
@Node231
@Dododede23
Malaaaakads
Mohamedben392
Ggfigt
Maya_ADS1
zeyad3112
@nonaads
@mai_promoter
@ADSONLYF
@Mohamed_ads97
@Maha2210
"""

lines = raw_text.strip().split('\n')
unique_leads = {}

for line in lines:
    line = line.strip()
    if not line:
        continue
    
    # Extract handle
    parts = line.split()
    first_token = parts[0].lstrip('@').strip()
    name_hint = " ".join(parts[1:]).strip() if len(parts) > 1 else ""
    
    clean_handle = first_token.lower()
    
    if clean_handle not in unique_leads:
        unique_leads[clean_handle] = {
            "username": f"@{first_token}",
            "handle_clean": clean_handle,
            "name_hint": name_hint or first_token
        }
    elif name_hint and not unique_leads[clean_handle]["name_hint"]:
        unique_leads[clean_handle]["name_hint"] = name_hint

leads_list = list(unique_leads.values())
print(f"Total raw items: {len(lines)}")
print(f"Total unique deduplicated advertisers: {len(leads_list)}")

for i, l in enumerate(leads_list, 1):
    print(f"{i:2d}. {l['username']:<22} | Name: {l['name_hint']}")

with open("autotele_target_advertisers.json", "w", encoding="utf-8") as f:
    json.dump(leads_list, f, ensure_ascii=False, indent=2)

print("\nSaved deduplicated list to autotele_target_advertisers.json")
