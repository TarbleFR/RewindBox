void timing_test() {
    using namespace rpcs3::ios::shader_timing;
    SlowOperations recorder;
    assert(pipeline_context.properties==0);
    {
        PipelineContextScope outer({1,2,3,4,5});
        {PipelineContextScope inner({6,7,8,9,10});recorder.record(Stage::graphics,10,50010);}
        recorder.record(Stage::graphics,20,50020);
        recorder.record(Stage::source,20,50020);
        recorder.record(Stage::graphics,30,50029); // below threshold
    }
    auto sample=recorder.take();assert(sample.captured && sample.size==3);
    assert(sample.events[0].pipeline.properties==6 && sample.events[1].pipeline.properties==1);
    assert(sample.events[2].pipeline.properties==0 && pipeline_context.properties==0);
    try {PipelineContextScope scope({88,0,0,0,0});throw 1;} catch(int) {}
    assert(pipeline_context.properties==0);
    for(unsigned i=0;i<40;++i) recorder.record(Stage::graphics,100,100100);
    sample=recorder.take();assert(sample.size==32 && sample.dropped==8);
    std::array<std::thread,8> workers;
    for(unsigned i=0;i<workers.size();++i) workers[i]=std::thread([&,i] {
        PipelineContextScope scope({i+1,2,3,4,5});
        for(unsigned j=0;j<100;++j) recorder.record(Stage::graphics,100,200100);
    });
    for(auto& worker:workers) worker.join();
    sample=recorder.take();
    assert(sample.captured && sample.size+sample.dropped==800);
    for(unsigned i=0;i<sample.size;++i) assert(sample.events[i].pipeline.properties>=1 && sample.events[i].pipeline.properties<=8 && sample.events[i].pipeline.flags==5);
    assert(pipeline_context.properties==0);
}
