template<class T> T handle(u64 n) {return reinterpret_cast<T>(static_cast<uintptr_t>(n));}
struct Report {
 u64 initial_bytes=0,buffer_only_bytes=0,queue_entries=0,flush_entries=0;
 std::vector<std::array<u64,8>> writes;
};
Report run() {
 auto& manager=g_fxo->get<descriptors::dispatch_manager>();
 manager.destroy();driver_writes.clear();
 Report result;
 device.mask=0;
 {
  allocated_bytes=0;descriptor_set set;set=handle<VkDescriptorSet>(1);
  result.initial_bytes=allocated_bytes;
  auto* ptr=set.store(VkDescriptorBufferInfo{handle<VkBuffer>(2),3,4});
  result.buffer_only_bytes=allocated_bytes;
  assert(ptr->range==4 && set.m_buffer_info_pool.capacity()==16448);
  rsx::simple_array<VkWriteDescriptorSet> writers;
  VkWriteDescriptorSet w{};w.sType=VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;w.dstSet=set.value();w.dstBinding=0;w.descriptorCount=1;
  w.descriptorType=VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER;w.pBufferInfo=ptr;writers.push_back(w);
  set.push(writers,1u<<VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER);set.on_bind();
  assert(set.cache_id()==1);
  // Flush invalidates template storage; a new generation re-stores its payload.
  const auto generation=set.cache_id();
  allocated_bytes=0;
  set=handle<VkDescriptorSet>(3);
  auto* second=set.store(VkDescriptorBufferInfo{handle<VkBuffer>(4),5,6});
  assert(allocated_bytes==0 && generation==set.cache_id());
  writers[0].dstSet=set.value();writers[0].pBufferInfo=second;
  set.push(writers,1u<<VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER);set.on_bind();assert(set.cache_id()==generation+1);
  // Exercise each direct push and image-array overload.
  set.push(handle<VkBufferView>(11),VK_DESCRIPTOR_TYPE_UNIFORM_TEXEL_BUFFER,0);
  set.push(VkDescriptorBufferInfo{handle<VkBuffer>(12),13,14},VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,1);
  set.push(VkDescriptorImageInfo{handle<VkSampler>(15),handle<VkImageView>(16),VK_IMAGE_LAYOUT_GENERAL},VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER,2);
  VkDescriptorImageInfo image_array[2]={{handle<VkSampler>(21),handle<VkImageView>(22),VK_IMAGE_LAYOUT_GENERAL},{handle<VkSampler>(23),handle<VkImageView>(24),VK_IMAGE_LAYOUT_GENERAL}};
  set.push(image_array,2,VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER,3);
  set.on_bind();
  rsx::simple_array<VkCopyDescriptorSet> copies;
  VkCopyDescriptorSet copy{};copy.sType=VK_STRUCTURE_TYPE_COPY_DESCRIPTOR_SET;
  copy.srcSet=handle<VkDescriptorSet>(70);copy.dstSet=set.value();copy.srcBinding=4;copy.dstBinding=5;copy.descriptorCount=1;
  copies.push_back(copy);set.push(copies,1u<<VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER);set.on_bind();
  set.push(descriptor_set_dynamic_offset_t{2,77});assert(set.m_dynamic_offsets.size()==3 && set.m_dynamic_offsets[2]==77);
 }
 // Deferred updates: every pointer remains valid up to the old full capacity,
 // even as other pool types are first used and the queue is flushed later.
 device.mask=~u64{0};
 {
  descriptor_set set;set=handle<VkDescriptorSet>(31);
  auto* first_image=set.store(VkDescriptorImageInfo{handle<VkSampler>(32),handle<VkImageView>(33),VK_IMAGE_LAYOUT_GENERAL});
  auto* first_buffer=set.store(VkDescriptorBufferInfo{handle<VkBuffer>(34),35,36});
  auto* first_view=set.store(handle<VkBufferView>(37));
  for(u32 i=1;i<16448;++i) {
   auto* im=set.store(VkDescriptorImageInfo{handle<VkSampler>(100+i),handle<VkImageView>(200+i),VK_IMAGE_LAYOUT_GENERAL});
   auto* bu=set.store(VkDescriptorBufferInfo{handle<VkBuffer>(300+i),400+i,500+i});
   auto* vi=set.store(handle<VkBufferView>(600+i));
   assert(im==first_image+i && bu==first_buffer+i && vi==first_view+i);
  }
  assert(first_image->sampler==handle<VkSampler>(32) && first_buffer->range==36 && *first_view==handle<VkBufferView>(37));
  rsx::simple_array<VkWriteDescriptorSet> writers;
  VkWriteDescriptorSet w{};w.sType=VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;w.dstSet=set.value();w.dstBinding=0;w.descriptorCount=1;
  w.descriptorType=VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER;w.pBufferInfo=first_buffer;writers.push_back(w);
  set.push(writers,1u<<VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER);set.on_bind();
  // Storage pressure synchronously flushes the full cache without losing data.
  assert(set.cache_id()==1);
  rsx::simple_array<VkDescriptorImageInfo> images;
  for(u32 i=0;i<64;++i) images.push_back({handle<VkSampler>(1000+i),handle<VkImageView>(2000+i),VK_IMAGE_LAYOUT_GENERAL});
  auto* contiguous=set.store(images);
  assert(contiguous[63].imageView==handle<VkImageView>(2063));
  set.push(contiguous,64,VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER,5);
  set.flush();
 }
 // One object may queue thousands of different sets before a global flush.
 // Keeping only its first registration preserves the exact driver write order.
 {
  descriptor_set set;set=handle<VkDescriptorSet>(40);
  for(u32 i=0;i<10000;++i) {
   set=handle<VkDescriptorSet>(4000+i);
   set.push(VkDescriptorBufferInfo{handle<VkBuffer>(5000+i),i,64},VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER,0);
   set.on_bind();
  }
  result.queue_entries=manager.m_notification_list.size();
  result.flush_entries=manager.m_notification_list.size();
  manager.flush_all();assert(manager.m_notification_list.empty());
  set.push(VkDescriptorBufferInfo{handle<VkBuffer>(90),91,92},VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER,0);set.on_bind();
  assert(manager.m_notification_list.size()==1);
  manager.deregister(&set);assert(manager.m_notification_list.empty());
  set.on_bind();assert(manager.m_notification_list.size()==1);
  manager.destroy();assert(manager.m_notification_list.empty());
  set.on_bind();assert(manager.m_notification_list.size()==1);manager.flush_all();
 }
 // Queue membership uses only the manager mutex; duplicate concurrent
 // registrations do not race its flag. No descriptor payload is mutated here.
 {
  descriptor_set set;set=handle<VkDescriptorSet>(100);
  std::array<std::thread,4> threads;
  for(auto& thread:threads) thread=std::thread([&] {for(u32 i=0;i<5000;++i)manager.register_(&set);});
  for(auto& thread:threads)thread.join();
  manager.flush_all();assert(manager.m_notification_list.empty());
  manager.register_(&set);manager.deregister(&set);assert(manager.m_notification_list.empty());
 }
 // Swap changes handles, not queue-object ownership or pending destinations.
 {
  descriptor_set first,second;first=handle<VkDescriptorSet>(110);second=handle<VkDescriptorSet>(111);
  first.push(VkDescriptorBufferInfo{handle<VkBuffer>(112),113,114},VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER,0);first.on_bind();
  second.push(VkDescriptorBufferInfo{handle<VkBuffer>(115),116,117},VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER,0);second.on_bind();
  first.swap(second);
  assert(first.value()==handle<VkDescriptorSet>(111) && second.value()==handle<VkDescriptorSet>(110));
  manager.flush_all();
 }
 manager.destroy();
 result.writes=driver_writes;
 return result;
}
