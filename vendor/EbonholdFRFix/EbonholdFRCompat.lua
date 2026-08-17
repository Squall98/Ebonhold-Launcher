-- EbonholdFR Compat (genere)
-- La grosse MAJ du serveur a ajoute une interface custom (patch-D/M) qui utilise
-- des globales chargees cote enUS mais absentes du pack frFR (2012) -> erreurs Lua.
-- Cet addon recree ces globales pour stabiliser le jeu en francais.

-- Globales manquantes en frFR (secours anglais pour eviter les nil)
  ARMOR_COLON = ARMOR_COLON or "Armor:";
  ATTACK_POWER_COLON = ATTACK_POWER_COLON or "Power:";
  ATTACK_SPEED_COLON = ATTACK_SPEED_COLON or "Attack Speed (seconds):";
  BINDING_NAME_TOGGLELFGTAB = BINDING_NAME_TOGGLELFGTAB or "Toggle LFG Pane";
  BINDING_NAME_TOGGLELFMTAB = BINDING_NAME_TOGGLELFMTAB or "Toggle LFM Pane";
  CHAT_NOT_IN_LFG_NOTICE = CHAT_NOT_IN_LFG_NOTICE or "[%s] You must be queued in looking for group before joining this channel.";
  CONFIRM_LFG_REMOVE_LAST_ROLE = CONFIRM_LFG_REMOVE_LAST_ROLE or "Removing your last role will cause you to leave all Looking For Group queues. Do you want to remove your last role?";
  DAMAGE_COLON = DAMAGE_COLON or "Damage:";
  DEFENSE_COLON = DEFENSE_COLON or "Defense:";
  ERR_MATACHMAKING_MEMBER_STILL_IN_QUEUE = ERR_MATACHMAKING_MEMBER_STILL_IN_QUEUE or "Looking for a new party in the LFG matchmaking system.";
  ERR_MATCHMAKING_AUTOJOIN_FAILED = ERR_MATCHMAKING_AUTOJOIN_FAILED or "Group no longer available.";
  ERR_MATCHMAKING_AUTOJOIN_FAILED_NO_PLAYER = ERR_MATCHMAKING_AUTOJOIN_FAILED_NO_PLAYER or "Matched Player(s) have gone offline.";
  ERR_MATCHMAKING_IN_PROGRESS = ERR_MATCHMAKING_IN_PROGRESS or "You are still seeking more members through the LFG matchmaking system.";
  ERR_MATCHMAKING_MADE_LEADER = ERR_MATCHMAKING_MADE_LEADER or "You are the party leader!";
  ERR_MATCHMAKING_MEMBER_ADDED_S = ERR_MATCHMAKING_MEMBER_ADDED_S or "%s has been added to the group by the LFG matchmaking system.";
  ERR_MATCHMAKING_MEMBER_STILL_IN_QUEUE = ERR_MATCHMAKING_MEMBER_STILL_IN_QUEUE or "Looking for a new party in the LFG matchmaking system.";
  ERR_MATCHMAKING_MUST_BE_LEADER = ERR_MATCHMAKING_MUST_BE_LEADER or "You must be the party leader to use LFM and autojoin.";
  ERR_MATCHMAKING_NOT_LEADER = ERR_MATCHMAKING_NOT_LEADER or "Only the party leader can leave the LFM matchmaking system.";
  ERR_MATCHMAKING_NO_RAID_GROUP = ERR_MATCHMAKING_NO_RAID_GROUP or "You cannot use the LFG matchmaking system while in a raid group.";
  ERR_MATCHMAKING_OTHER_MEMBER_LEFT = ERR_MATCHMAKING_OTHER_MEMBER_LEFT or "Party member has left.  Looking for a new party in the LFG matchmaking system.";
  ERR_MATCHMAKING_OTHER_TIMEDOUT = ERR_MATCHMAKING_OTHER_TIMEDOUT or "Matchmaking timed out waiting for other player.";
  ERR_MATCHMAKING_PARTY_KICKED_FROM_QUEUE = ERR_MATCHMAKING_PARTY_KICKED_FROM_QUEUE or "Party member removed from group - party removed from the matchmaking system.";
  ERR_MATCHMAKING_PENDING_INVITE_S = ERR_MATCHMAKING_PENDING_INVITE_S or "The LFG system has matched you to a group for %s.";
  ERR_MATCHMAKING_PENDING_MATCH_S = ERR_MATCHMAKING_PENDING_MATCH_S or "The LFG system is waiting to complete the match for %s.";
  ERR_MATCHMAKING_SUCCESS = ERR_MATCHMAKING_SUCCESS or "Your group is complete, you have left the LFG matchmaking system.";
  ERR_MATCHMAKING_TIMEDOUT = ERR_MATCHMAKING_TIMEDOUT or "Matchmaking timed out.";
  LFG_BUTTON = LFG_BUTTON or "Looking For Group/Looking For More";
  LOOKING_FOR_GROUP = LOOKING_FOR_GROUP or "Looking For Group";
  NO_ROLE_SELECTED = NO_ROLE_SELECTED or "You must select one or more roles before you can join Looking For Group or Looking For More.";
  OPTION_TOOLTIP_UNIT_NAME_COMPANIONS = OPTION_TOOLTIP_UNIT_NAME_COMPANIONS or "Show companions' names in the game world.";
  OPTION_TOOLTIP_UNIT_NAME_ENEMY_CREATIONS = OPTION_TOOLTIP_UNIT_NAME_ENEMY_CREATIONS or "Show enemy creations' names in the game world.";
  OPTION_TOOLTIP_UNIT_NAME_FRIENDLY_CREATIONS = OPTION_TOOLTIP_UNIT_NAME_FRIENDLY_CREATIONS or "Show friendly creations' names in the game world.";
  SLASH_LOOKINGFORGROUP1 = SLASH_LOOKINGFORGROUP1 or "/lfg";
  SLASH_LOOKINGFORGROUP2 = SLASH_LOOKINGFORGROUP2 or "/lfg";
  SLASH_LOOKINGFORMORE1 = SLASH_LOOKINGFORMORE1 or "/lfm";
  SLASH_LOOKINGFORMORE2 = SLASH_LOOKINGFORMORE2 or "/lfm";
  SPELL_BONUS_COLON = SPELL_BONUS_COLON or "Spell Bonus:";
  UNIT_NAME_COMPANIONS = UNIT_NAME_COMPANIONS or "Companions";
  UNIT_NAME_ENEMY_CREATIONS = UNIT_NAME_ENEMY_CREATIONS or "Creations";
  UNIT_NAME_FRIENDLY_CREATIONS = UNIT_NAME_FRIENDLY_CREATIONS or "Creations";

-- Globales custom absentes des DEUX locales : secours anglais (fill-nil)
PLAYER_LEVEL_SPEC = PLAYER_LEVEL_SPEC or "Level %d %s %s";
PLAYER_LEVEL_NO_SPEC = PLAYER_LEVEL_NO_SPEC or "Level %d %s";
RESISTANCE_TOOLTIP_SUBTEXT2 = RESISTANCE_TOOLTIP_SUBTEXT2 or "At level 80, resistance reduces spell damage by %s%%.";
PAPERDOLLFRAME_ILEVEL_TOOLTIP_1 = PAPERDOLLFRAME_ILEVEL_TOOLTIP_1 or "Item Level: %d";

-- Libelles francais, appliques SEULEMENT si le client tourne en frFR
if GetLocale() == "frFR" then
  ARMOR_COLON = "Armure :";
  ATTACK_POWER_COLON = "Puissance d'attaque :";
  ATTACK_SPEED_COLON = "Vitesse d'attaque (secondes) :";
  DAMAGE_COLON = "Dégâts :";
  DEFENSE_COLON = "Défense :";
  PLAYER_LEVEL_SPEC = "Niveau %d %s %s";
  PLAYER_LEVEL_NO_SPEC = "Niveau %d %s";
  RESISTANCE_TOOLTIP_SUBTEXT2 = "Au niveau 80, la résistance réduit les dégâts de sorts de %s%%.";
  PAPERDOLLFRAME_ILEVEL_TOOLTIP_1 = "Niveau d'objet : %d";
end

-- La MAJ a retire/renomme ToggleSpellBook cote frFR : on le redefinit si absent.
if not ToggleSpellBook then
    function ToggleSpellBook(bookType)
        if InCombatLockdown() then return end
        if not SpellBookFrame then return end
        local same = SpellBookFrame:IsShown() and SpellBookFrame.bookType == bookType
        HideUIPanel(SpellBookFrame)
        if not same then
            SpellBookFrame.bookType = bookType
            ShowUIPanel(SpellBookFrame)
        end
    end
end
