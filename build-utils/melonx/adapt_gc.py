"""Give the .NET GC a gen2 budget it can work with during a game.

Hogwarts Legacy, 27 October 2026 (Build 564 app.log): from about 50 s into
the session the background GC thread (.NET_BGC) used 46-72 % of a core for the
rest of the 727 s, the game fell from 30 to 6-13 FPS, and 4,408 presented
frames came more than 40 ms apart before the device was even warm.

The engine is published with System.GC.ConserveMemory=9. In the .NET 10 GC
(gc.cpp, desired_new_allocation) a setting of N caps gen2 growth at
((10 / N) - 1) * 0.5 + 1 of the surviving size: 1.056 for 9, so a background
gen2 collection, which marks the whole heap, starts after promotions or large
objects worth 5.6 % of it. generation_to_condemn also turns every gen2
collection whose gen2+LOH fragmentation exceeds 1 - N / 10 (10 %) into a
blocking compacting one. 5 is the value the GC itself uses when it adapts to
the application size: growth up to 50 % before the next gen2 collection, and
compaction past 50 % fragmentation. Fail closed on drift.
"""
from adapt_session import once


def apply(source):
    project = source / 'src/Ryujinx.Library/Ryujinx.Library.csproj'
    once(project, '<RuntimeHostConfigurationOption Include="System.GC.ConserveMemory" Value="9" />',
         '<RuntimeHostConfigurationOption Include="System.GC.ConserveMemory" Value="5" />')
    return [project]
