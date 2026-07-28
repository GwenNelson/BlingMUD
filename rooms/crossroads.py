from core import *

from npcs.brave_sir_knight import BraveSirKnight

class Crossroads(Room):
   """ Built for Brave Sir Knight to guard
   """
   def __init__(self):
       Room.__init__(self,"crossroads","The lonely crossroads",
                     "Four ancient roads meet upon a lonely stretch of open country, their worn stones bearing the marks of countless travellers who have passed this way over generations. A weathered signpost stands at the centre, its faded carvings pointing toward distant kingdoms whose names have long since become unfamiliar.\r\n"
                     "A broad oak offers welcome shade beside a clear stone well, while a small campfire smoulders nearby. Fresh water rests in a bucket, and a neatly stacked pile of firewood suggests that someone still tends this forgotten place with quiet diligence.\r\n"
                    "Though no town lies within sight, the crossroads feels strangely safe. Birds sing from the hedgerows, the breeze carries the scent of wildflowers and woodsmoke, and every path seems to promise another adventure beyond the horizon.\r\n"
                    "Standing watch over it all is Brave Sir Knight, whose unwavering vigil has made this lonely place a haven for weary souls. He greets every traveller with kindness, offers what simple aid he can, and asks only for news of the roads beyond the crossroads he has sworn to protect.\r\n")
       self.knight = BraveSirKnight()
       self.add_npc(self.knight)
