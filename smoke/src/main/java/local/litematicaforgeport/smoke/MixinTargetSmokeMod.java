package local.litematicaforgeport.smoke;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

import net.minecraftforge.fml.common.Mod;

@Mod(MixinTargetSmokeMod.MOD_ID)
public final class MixinTargetSmokeMod
{
    public static final String MOD_ID = "forgeportsmoke";

    public MixinTargetSmokeMod()
    {
        ClassLoader loader = MixinTargetSmokeMod.class.getClassLoader();
        int loaded = 0;

        try (InputStream in = loader.getResourceAsStream("mixin-targets.txt"))
        {
            if (in == null)
            {
                throw new IllegalStateException("mixin-targets.txt is missing from the smoke harness");
            }

            try (BufferedReader reader = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8)))
            {
                String target;
                while ((target = reader.readLine()) != null)
                {
                    target = target.trim();
                    if (target.isEmpty() || target.startsWith("#"))
                    {
                        continue;
                    }

                    try
                    {
                        // Loading without initialization still sends the class through
                        // ModLauncher/Mixin transformation, which is what this test needs.
                        Class.forName(target, false, loader);
                        loaded++;
                    }
                    catch (Throwable throwable)
                    {
                        throw new RuntimeException("Failed while force-loading configured mixin target " + target, throwable);
                    }
                }
            }
        }
        catch (RuntimeException exception)
        {
            throw exception;
        }
        catch (Exception exception)
        {
            throw new RuntimeException("Failed to run mixin target smoke harness", exception);
        }

        if (loaded < 60)
        {
            throw new IllegalStateException("Only force-loaded " + loaded + " mixin targets");
        }

        System.out.println("[ForgePortSmoke] Successfully force-loaded " + loaded + " configured mixin targets.");
    }
}
