using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.Loader;
using System.Text.Json;
var directory=Path.GetDirectoryName(Path.GetFullPath(args[0]));
AssemblyLoadContext.Default.Resolving += (context,name) => {
 var file=Path.Combine(directory,name.Name+".dll");
 return File.Exists(file)?context.LoadFromAssemblyPath(file):null;
};
var assembly=AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.GetFullPath(args[0]));
var helper=assembly.GetType("Ryujinx.Graphics.GAL.Multithreading.CommandHelper",true);
int maximum=(int)helper.GetMethod("GetMaxCommandSize",BindingFlags.Public|BindingFlags.Static).Invoke(null,null);
var commandSizes=assembly.GetTypes().Where(t=>t.Name is "TextureArraySetTexturesCommand" or "TextureArraySetSamplersCommand" or "ImageArraySetImagesCommand")
 .ToDictionary(t=>t.Name,t=>(int)typeof(Unsafe).GetMethod("SizeOf").MakeGenericMethod(t).Invoke(null,null));
Console.WriteLine(JsonSerializer.Serialize(new {maximum, alignedStride=(maximum+3)&~3, commandSizes}));
