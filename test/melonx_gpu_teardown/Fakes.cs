using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Reflection.Emit;

// Inert GAL doubles: no Vulkan, Metal or GPU. Every member returns its type's
// default, except GAL interfaces (textures, views, windows), which return new
// doubles so the production texture code can keep and release them.
public static class Fake
{
    private static readonly ModuleBuilder Module = AssemblyBuilder
        .DefineDynamicAssembly(new AssemblyName("MeloNXGalDoubles"), AssemblyBuilderAccess.Run)
        .DefineDynamicModule("MeloNXGalDoubles");
    private static readonly ConcurrentDictionary<Type, Type> Types = new();
    private static readonly MethodInfo ResolveMethod = typeof(Fake).GetMethod(nameof(Resolve), BindingFlags.Public | BindingFlags.Static)!;
    private static readonly MethodInfo RecordMethod = typeof(Fake).GetMethod(nameof(Record), BindingFlags.Public | BindingFlags.Static)!;
    public static readonly ConcurrentQueue<string> Calls = new();

    public static void Record(string member) => Calls.Enqueue(member);

    public static T Create<T>() => (T)Create(typeof(T));

    public static object Create(Type type) => Activator.CreateInstance(Types.GetOrAdd(type, Build))!;

    public static object Resolve(RuntimeTypeHandle handle)
    {
        Type type = Type.GetTypeFromHandle(handle)!;
        return type.IsInterface && type.Namespace?.StartsWith("Ryujinx.Graphics.GAL") == true ? Create(type) : null!;
    }

    private static Type Build(Type contract)
    {
        TypeBuilder builder = Module.DefineType("Fake" + contract.Name + Types.Count, TypeAttributes.Public | TypeAttributes.Sealed);
        IEnumerable<Type> contracts = new[] { contract }.Concat(contract.GetInterfaces());
        foreach (Type item in contracts.Distinct())
        {
            builder.AddInterfaceImplementation(item);
            foreach (MethodInfo method in item.GetMethods())
            {
                Type[] parameters = method.GetParameters().Select(p => p.ParameterType).ToArray();
                MethodBuilder body = builder.DefineMethod(item.FullName + "." + method.Name,
                    MethodAttributes.Private | MethodAttributes.Virtual | MethodAttributes.Final | MethodAttributes.HideBySig | MethodAttributes.NewSlot,
                    method.ReturnType, parameters);
                if (method.IsGenericMethodDefinition)
                {
                    body.DefineGenericParameters(method.GetGenericArguments().Select(a => a.Name).ToArray());
                }
                ILGenerator il = body.GetILGenerator();
                il.Emit(OpCodes.Ldstr, contract.Name + ":" + item.Name + "." + method.Name);
                il.Emit(OpCodes.Call, RecordMethod);
                Type result = method.ReturnType;
                if (result == typeof(void))
                {
                    il.Emit(OpCodes.Ret);
                }
                else if (result.IsInterface)
                {
                    il.Emit(OpCodes.Ldtoken, result);
                    il.Emit(OpCodes.Call, ResolveMethod);
                    il.Emit(OpCodes.Castclass, result);
                    il.Emit(OpCodes.Ret);
                }
                else if (!result.IsValueType || result.IsByRef)
                {
                    il.Emit(OpCodes.Ldnull);
                    il.Emit(OpCodes.Ret);
                }
                else
                {
                    LocalBuilder local = il.DeclareLocal(result);
                    il.Emit(OpCodes.Ldloca, local);
                    il.Emit(OpCodes.Initobj, result);
                    il.Emit(OpCodes.Ldloc, local);
                    il.Emit(OpCodes.Ret);
                }
                builder.DefineMethodOverride(body, method);
            }
        }
        return builder.CreateType();
    }
}
