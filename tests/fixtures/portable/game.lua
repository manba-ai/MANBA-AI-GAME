-- @library-controller-v2
-- @game-hud-v1
-- @records-key 83f33cca911fb5d0724f920daa3c482a2482cc0b620cacd22191afc55b5638c6
-- Deterministic portability fixture. Rules are frozen before this is copied into the build.
local G,P
local positions={1,3,2}
local function save() P.saved=math.max(P.saved,G.score);P.best=math.max(P.best,P.saved) end
local function reset(mode)
 G={mode=mode,status=mode=='play' and 'running' or 'paused',ticks=0,score=0,lives=3,
    lane=2,parcel_lane=1,elapsed=0,spawn=1,exit_requested=false}
end
function init() P={saved=0,best=0,error=false,invalid=false};reset('menu') end
function input(key)
 if key=='restart' then save();reset('menu');return end
 if key=='stop' then save();if G.mode=='play' then G.mode='pause' end;G.status='paused';return end
 if key=='pause' then
  if G.mode=='play' then save();G.mode='pause';G.status='paused'
  elseif G.mode=='pause' then G.mode='play';G.status='running' end;return
 end
 if G.mode=='menu' then
  if key=='a' or key=='action' then reset('play')
  elseif key=='y' then G.mode='help'
  elseif key=='b' then G.exit_requested=true end
 elseif G.mode=='help' then
  if key=='a' or key=='action' then reset('play')
  elseif key=='b' or key=='y' then G.mode='menu' end
 elseif G.mode=='pause' then
  if key=='a' or key=='action' then G.mode='play';G.status='running'
  elseif key=='x' then save();reset('play')
  elseif key=='y' then save();reset('menu')
  elseif key=='b' then save();G.exit_requested=true end
 elseif G.mode=='result' then
  if key=='a' or key=='action' or key=='x' then save();reset('play')
  elseif key=='y' then save();reset('menu')
  elseif key=='b' then save();G.exit_requested=true;G.status='paused' end
 elseif G.mode=='play' then
  if key=='left' then G.lane=math.max(1,G.lane-1)
  elseif key=='right' then G.lane=math.min(3,G.lane+1) end
 end
end
function update(dt)
 if G.mode~='play' or G.status~='running' or G.exit_requested or dt<=0 then return false end
 G.ticks=G.ticks+1;G.elapsed=G.elapsed+dt
 if G.elapsed>=1000 then
  if G.lane==G.parcel_lane then G.score=G.score+1 else G.lives=G.lives-1 end
  G.spawn=G.spawn+1;G.parcel_lane=positions[(G.spawn-1)%3+1];G.elapsed=G.elapsed-1000
  if G.lives==0 or G.score>=3 then
   G.mode='result';G.status=G.score>=3 and 'won' or 'over';save()
  end
 end
 return true
end
function draw()
 screen.clear(0x0863)
 screen.text(12,12,'LANE COURIER',0xff38,2)
 if G.mode=='play' then
  screen.text(12,34,'SCORE '..G.score..'  LIVES '..G.lives,0xff38,1)
  for lane=1,3 do screen.rect(32+(lane-1)*96,55,64,160,0x10a5) end
  local px=64+(G.parcel_lane-1)*96
  local py=60+math.floor(G.elapsed*0.12)
  if game_data and game_data.sprites and game_data.sprites.parcel then
   screen.sprite(game_data.sprites.parcel,px-8,py,0)
  else screen.rect(px-8,py,16,16,0xed68) end
  screen.rect(50+(G.lane-1)*96,200,28,8,0x3db5)
 else
  screen.rect(8,70,304,2,0xed68)
  local title=G.mode=='menu' and 'COLLECT THREE PARCELS' or G.mode=='pause' and 'PAUSED'
   or G.mode=='help' and 'HOW TO PLAY' or G.score>=3 and 'YOU WIN' or 'GAME OVER'
  screen.text(16,86,title,0xff38,2)
  screen.text(16,120,'BEST '..P.best..'   SCORE '..G.score,0xed68,1)
  local hint=G.mode=='help' and 'LEFT / RIGHT: LANES. MISS 3: LOSE.'
   or G.mode=='pause' and 'A RESUME  X RETRY  Y TITLE  B EXIT'
   or G.mode=='result' and 'A RETRY   Y TITLE   B EXIT' or 'A START   Y HELP   B EXIT'
  screen.text(16,158,hint,0xff38,1)
  screen.rect(8,186,304,2,0xed68)
 end
end
function snapshot()
 return {status=G.status,mode=G.mode,ticks=G.ticks,score=G.score,lives=G.lives,
  lane=G.lane,elapsed=G.elapsed,parcel_lane=G.parcel_lane,menu_navigation=G.mode~='play',exit_requested=G.exit_requested}
end
function records_export() if P.invalid then return nil end;return P.saved==0 and 'R1|' or string.format('R1|0,%d,0,-1;',P.saved) end
function records_restore(raw)
 local n=raw=='R1|' and 0 or type(raw)=='string' and tonumber(raw:match('^R1|0,(%d+),0,%-1;$'))
 if not n or n>1000000000 then P.invalid=true;P.error=true;return false end
 P.best=math.max(P.best,n);P.saved=math.max(P.saved,n);P.invalid=false;P.error=false;return true
end
function records_storage(ok) P.error=not ok end
function records_finish() save() end
