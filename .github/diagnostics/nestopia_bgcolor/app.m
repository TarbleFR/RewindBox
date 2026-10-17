#import <UIKit/UIKit.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include "LibretroCrashCapture.h"
int core_probe_main(int, char **);
@interface App : UIResponder <UIApplicationDelegate>
@property(nonatomic,strong) UIWindow *window;
@end
@implementation App
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options {
  self.window=[[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
  self.window.rootViewController=[UIViewController new];[self.window makeKeyAndVisible];
  NSString *documents=NSSearchPathForDirectoriesInDomains(NSDocumentDirectory,NSUserDomainMask,YES).firstObject;
  freopen([[documents stringByAppendingPathComponent:@"probe.log"] fileSystemRepresentation],"w",stdout);
  freopen([[documents stringByAppendingPathComponent:@"stderr.log"] fileSystemRepresentation],"w",stderr);
  int fd=open([[documents stringByAppendingPathComponent:@"fault.log"] fileSystemRepresentation],O_WRONLY|O_CREAT|O_TRUNC,0600);
  LibretroInstallCrashCapture(fd);
  dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{
    const char *filter=getenv("NEOSTATION_NTSC_FILTER");
    NSString *path=[NSBundle.mainBundle.privateFrameworksPath stringByAppendingPathComponent:@"nestopia_libretro.framework/nestopia_libretro"];
    char *args[]={"probe",(char *)path.fileSystemRepresentation,(char *)(filter?:"composite"),NULL};
    int result=core_probe_main(3,args);
    printf("EXIT=%d\n",result);fflush(stdout);fflush(stderr);exit(result);
  });
  return YES;
}
@end
int main(int argc,char **argv){@autoreleasepool{return UIApplicationMain(argc,argv,nil,NSStringFromClass(App.class));}}
