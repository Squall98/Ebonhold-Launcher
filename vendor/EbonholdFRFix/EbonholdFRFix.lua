-- Ebonhold FR Fix
-- Quand le client est en francais, les PNJ custom (forge, call board) s'affichent
-- avec un nom traduit. L'addon ProjectEbonhold compare ce nom a la chaine ANGLAISE
-- exacte pour ouvrir son interface ; en francais la comparaison echoue et on tombe
-- sur le dialogue par defaut. Cet addon additionnel re-declenche la bonne fenetre
-- quand il reconnait le nom francais. Purement additif : ne modifie aucun fichier
-- d'Ebonhold, et ne se declenche jamais sur un client anglais (noms anglais ignores).

local function msg(t)
    if DEFAULT_CHAT_FRAME then
        DEFAULT_CHAT_FRAME:AddMessage("|cff33ff99[FRFix]|r " .. tostring(t))
    end
end

-- Noms FR exacts des PNJ custom (octets UTF-8 : e accent aigu = \195\169).
-- On ne matche QUE le francais : sur un client anglais, ProjectEbonhold gere deja.
local ANVIL_NAMES = {
    ["Enclume enchant\195\169e"] = true,   -- "Enclume enchantee" -> forge / extraction d'affixes
}
local BOARD_NAMES = {
    -- nom FR du "Objectives Board" a confirmer en jeu via /frfix
}

local diag = false
local active = nil   -- "anvil" | "board" | nil

local function hideGossip()
    if GossipFrame then
        GossipFrame:SetAlpha(0)
        GossipFrame:EnableMouse(false)
        GossipFrame:ClearAllPoints()
        GossipFrame:SetPoint("TOPLEFT", UIParent, "BOTTOMRIGHT", 1000, -1000)
    end
end

local function restoreGossip()
    if GossipFrame then
        GossipFrame:SetAlpha(1)
        GossipFrame:EnableMouse(true)
        GossipFrame:ClearAllPoints()
        GossipFrame:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 16, -116)
    end
end

local function openAnvil()
    if EbonholdExtractionFrame then
        active = "anvil"
        hideGossip()
        EbonholdExtractionFrame:Show()
        return true
    end
    return false
end

local function openBoard()
    local PE = ProjectEbonhold
    if PE and PE.ObjectivesUI and PE.ObjectivesUI.DisplayObjectives and PE.ObjectivesService then
        active = "board"
        hideGossip()
        local objectives = PE.ObjectivesService.GetCurrentObjectives()
        if objectives and #objectives > 0 then
            PE.ObjectivesUI.DisplayObjectives(objectives)
        end
        return true
    end
    return false
end

local f = CreateFrame("Frame")
f:RegisterEvent("GOSSIP_SHOW")
f:RegisterEvent("GOSSIP_CLOSED")
f:SetScript("OnEvent", function(self, event)
    if event == "GOSSIP_SHOW" then
        if not GossipFrame or not GossipFrame:IsShown() then return end
        local npcName = GossipFrameNpcNameText and GossipFrameNpcNameText:GetText()
        if diag then msg("gossip PNJ = [" .. tostring(npcName) .. "]") end
        if npcName then
            if ANVIL_NAMES[npcName] then
                openAnvil()
            elseif BOARD_NAMES[npcName] then
                openBoard()
            end
        end
    elseif event == "GOSSIP_CLOSED" then
        if active then
            active = nil
            restoreGossip()
        end
    end
end)

-- /frfix : affiche le nom du prochain PNJ de dialogue (pour capturer un nom FR inconnu)
SLASH_FRFIX1 = "/frfix"
SlashCmdList["FRFIX"] = function()
    diag = not diag
    if diag then
        msg("diagnostic ON - ouvre un PNJ, son nom va s'afficher. Refais /frfix pour couper.")
    else
        msg("diagnostic OFF.")
    end
end
