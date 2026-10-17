-- @library-controller-v2
-- @game-hud-v1
-- @records-key 83f33cca911fb5d0724f920daa3c482a2482cc0b620cacd22191afc55b5638c6
-- @manba-template
-- Implement the authored rules, then remove the @manba-template marker.
function init() end
function input(key) end
function update(dt_ms) return false end
function draw() end
function snapshot()
 return {status='paused',ticks=0,score=0}
end
-- Add records_export, records_restore, records_storage and records_finish.
-- See docs/GAME_API.md from the project root.
